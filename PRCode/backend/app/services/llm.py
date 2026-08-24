"""
LLM service — routes user questions through RAG retrieval and then to the
selected provider (Claude / GPT-4o / Gemini).

This module implements an AI Gateway with:
- Model routing (small/medium/large)
- Token limit enforcement & context truncation
- Response caching to minimize duplicates
- API key validation before execution
"""

import httpx
import hashlib
import json
import asyncio
from typing import Optional

from app.services.rag import retrieve, format_chunks_for_prompt
from app.config import settings
from app.logger import log_ai_usage, logger

# ── Response Cache ───────────────────────────────────────────────────────────
_RESPONSE_CACHE = {}

def get_cache_key(system: str, messages: list[dict], provider: str, model: str) -> str:
    hash_input = json.dumps({"sys": system, "msg": messages, "prov": provider, "mod": model}, sort_keys=True)
    return hashlib.sha256(hash_input.encode()).hexdigest()

# ── Provider endpoint configs ────────────────────────────────────────────────
PROVIDERS = {
    "claude": {
        "url": "https://api.anthropic.com/v1/messages",
        "large": "claude-3-5-sonnet-20240620",
        "small": "claude-3-haiku-20240307",
    },
    "gpt": {
        "url": "https://api.openai.com/v1/chat/completions",
        "large": "gpt-4o",
        "small": "gpt-4o-mini",
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "large": "gemini-2.5-pro",
        "small": "gemini-2.5-flash",
    },
}

# ── Token limits & Truncation ────────────────────────────────────────────────
def estimate_tokens(text: str) -> int:
    return len(text) // 4  # rough estimate

def truncate_context(history: list[dict], context: str, max_tokens: int = 15000) -> tuple[list[dict], str]:
    new_history = list(history)
    # Prune history first
    history_tokens = sum(estimate_tokens(m["content"]) for m in new_history)
    while history_tokens > 2000 and len(new_history) > 2:
        popped = new_history.pop(0)
        history_tokens -= estimate_tokens(popped["content"])

    # Truncate RAG context if still too large
    context_tokens = estimate_tokens(context)
    if context_tokens > (max_tokens - 2000):
        allowed_chars = (max_tokens - 2000) * 4
        context = context[:allowed_chars] + "\n...[Context truncated due to token limits]..."
    return new_history, context

# ── System prompt builder ────────────────────────────────────────────────────
def _build_system_prompt(repo: str, issue: Optional[dict] = None, context: str = "") -> str:
    parts = [
        "You are PRGuard AI, a codebase learning assistant.",
        f"Repository: {repo}",
    ]
    if issue:
        parts.append(f'Focused issue: #{issue["number"]} — "{issue["title"]}"')
        if issue.get("body"):
            parts.append(f"Issue body:\n{issue['body'][:2000]}")

    if context and context != "No relevant code found.":
        parts.append(
            "Here are the most relevant code snippets from the repo "
            "(retrieved via RAG search):\n" + context
        )

    parts.append(
        "You are a Senior Full-Stack Engineer and codebase expert. "
        "Help developers understand codebases, fix issues, and contribute. "
        "Your responses should be technical, precise, and educational. "
        "Explain the 'why' behind code suggestions and provide detailed architectural context when relevant. "
        "Maintain a collaborative, conversational tone like an expert pair programmer. "
        "Use markdown for all formatting, and always put code inside triple-backtick blocks with the correct language identifier."
    )

    return "\n\n".join(parts)


# ── Provider-specific callers ────────────────────────────────────────────────
async def _call_claude(system: str, messages: list[dict], api_key: str, model: str, max_tokens: int = 1500) -> str:
    if not api_key:
        raise ValueError("Claude API key is missing or empty")
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    body = {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages}
    
    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
            resp = await client.post(PROVIDERS["claude"]["url"], headers=headers, json=body)
    except Exception as e:
        raise ValueError(f"Claude HTTP request failed: {str(e)}")
    
    try:
        data = resp.json()
    except Exception:
        data = {"error": {"message": resp.text[:500] or "Non-JSON response from Claude"}}
    if resp.status_code != 200 or "error" in data:
        detail = data.get("error", {}).get("message", str(data))
        raise ValueError(f"Claude API error ({resp.status_code}): {detail}")
    
    content = data.get("content", [])
    if not isinstance(content, list) or not content:
        raise ValueError(f"Claude API error: empty content in response")
    
    answer = "".join(block.get("text", "") for block in content)
    if not answer or answer.strip() == "":
        raise ValueError(f"Claude returned empty response")
    
    return answer


async def _call_openai(system: str, messages: list[dict], api_key: str, model: str, max_tokens: int = 1500) -> str:
    if not api_key:
        raise ValueError("OpenAI API key is missing or empty")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    oai_messages = [{"role": "system", "content": system}] + messages
    body = {"model": model, "max_tokens": max_tokens, "messages": oai_messages}
    
    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
            resp = await client.post(PROVIDERS["gpt"]["url"], headers=headers, json=body)
    except Exception as e:
        raise ValueError(f"OpenAI HTTP request failed: {str(e)}")
    
    try:
        data = resp.json()
    except Exception:
        data = {"error": {"message": resp.text[:500] or "Non-JSON response from OpenAI"}}
    if resp.status_code != 200 or "error" in data:
        detail = data.get("error", {}).get("message", str(data))
        raise ValueError(f"OpenAI API error ({resp.status_code}): {detail}")
    
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError(f"OpenAI API error: empty choices in response: {data}")
    
    answer = choices[0].get("message", {}).get("content", "")
    if not answer or answer.strip() == "":
        raise ValueError(f"OpenAI returned empty response")
    
    return answer


async def _call_gemini(system: str, messages: list[dict], api_key: str, model: str, max_tokens: int = 4096) -> str:
    if not api_key:
        raise ValueError("Gemini API key is missing or empty")
    
    url = PROVIDERS["gemini"]["url"].format(model=model)
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    
    logger.info(f"[Gemini] Requesting {model} with {len(messages)} messages")
    
    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=body)
    except Exception as e:
        raise ValueError(f"Gemini HTTP request failed: {str(e)}")
    
    try:
        data = resp.json()
    except Exception:
        data = {"error": {"message": resp.text[:500] or "Non-JSON response from Gemini"}}
    if resp.status_code != 200 or "error" in data:
        detail = data.get("error", {}).get("message", str(data))
        logger.error(f"[Gemini] API Error ({resp.status_code}): {detail}")
        raise ValueError(f"Gemini API error ({resp.status_code}): {detail}")
    
    candidates = data.get("candidates", [])
    if not candidates:
        finish_reason = data.get("promptFeedback", {}).get("blockReason", "Unknown")
        logger.error(f"[Gemini] No candidates returned. Block reason: {finish_reason}")
        raise ValueError(f"Gemini returned no candidates. Reason: {finish_reason}")
    
    answer = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    if not answer or answer.strip() == "":
        logger.warning(f"[Gemini] Empty response part. Finish reason: {candidates[0].get('finishReason')}")
        raise ValueError(f"Gemini returned empty response")
    
    return answer



# ── Router & Gateway ─────────────────────────────────────────────────────────

_CALLERS = {"claude": _call_claude, "gpt": _call_openai, "gemini": _call_gemini}
_KEY_MAP = {"claude": "ANTHROPIC_API_KEY", "gpt": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}

def _get_fallback_key(provider: str) -> str | None:
    attr = _KEY_MAP.get(provider)
    return getattr(settings, attr, None) if attr else None

def _resolve_provider_stack(provider_req: str):
    stack = ["claude", "gpt", "gemini"]
    req = "claude"
    if "gpt" in provider_req.lower() or "openai" in provider_req.lower():
        req = "gpt"
    elif "gemini" in provider_req.lower() or "google" in provider_req.lower():
        req = "gemini"
    if req in stack:
        stack.remove(req)
        stack.insert(0, req)
    return stack

# ── Main Entry ───────────────────────────────────────────────────────────────

async def generate(question: str, repo: str, history: list[dict], provider: str = "claude", api_key: str = "", issue: Optional[dict] = None, n_chunks: int = 8) -> dict:
    # ── 1. Validate API keys BEFORE doing expensive RAG ──────────────────────
    stack = _resolve_provider_stack(provider)
    valid_keys = {}
    
    # Log API key debug info
    logger.info(f"[LLM] Requested provider: {provider}")
    logger.info(f"[LLM] Provider stack: {stack}")
    logger.info(f"[LLM] Request API key provided: {'yes' if api_key else 'no'}")
    
    for p in stack:
        # Multi-user safety: use only the API key provided in this request.
        # Do not fall back to server-level provider keys for chat generation.
        k = api_key if (api_key and p == stack[0]) else None
        if k:
            valid_keys[p] = k
            logger.info(f"[LLM] Key available for {p}")
        else:
            logger.info(f"[LLM] No key available for {p}")

    if not valid_keys:
        error_detail = "All LLM providers failed or missing keys. Please provide an API key in Settings."
        logger.error(f"[LLM] {error_detail}")
        raise ValueError(error_detail)

    # ── 2. RAG Retrieval ─────────────────────────────────────────────────────
    chunks = []
    if n_chunks > 0:
        chunks = await retrieve(repo=repo, query=question, n_results=n_chunks)

    raw_context = format_chunks_for_prompt(chunks)

    # ── 3. Token Limits & History Truncation ─────────────────────────────────
    history, context = truncate_context(history, raw_context, max_tokens=15000)
    system = _build_system_prompt(repo=repo, issue=issue, context=context)
    messages = history + [{"role": "user", "content": question}]

    # Determine "Model Size" routing
    # For small, fast queries (e.g. general chat), use "small" model. 
    # For large contexts (e.g. full visualization), use "large" model.
    size_route = "large" if estimate_tokens(context) > 2000 or issue else "small"

    # ── 4. Cache Check ───────────────────────────────────────────────────────
    answer = None
    final_prov = stack[0]
    final_model = PROVIDERS[final_prov][size_route]

    for provider_candidate in stack:
        model_candidate = PROVIDERS[provider_candidate][size_route]
        cache_key = get_cache_key(system, messages, provider_candidate, model_candidate)
        if cache_key in _RESPONSE_CACHE:
            logger.info(f"[LLM Gateway] Cache hit for {provider_candidate} ({model_candidate})")
            log_ai_usage(provider_candidate, model_candidate, size_route, True)
            return {
                "answer": _RESPONSE_CACHE[cache_key],
                "chunks": chunks,
                "provider": provider_candidate,
            }

    # ── 5. Gateway Execution ─────────────────────────────────────────────────
    attempted = []
    last_error = None
    for p in stack:
        if p not in valid_keys: continue
        attempted.append(p)
        model = PROVIDERS[p][size_route]
        key = valid_keys[p]
        caller = _CALLERS[p]
        
        # Try each provider up to 2 times
        for attempt in range(2):
            try:
                logger.info(f"[LLM Gateway] Attempt {attempt+1} for {p} ({model})...")
                answer = await caller(system=system, messages=messages, api_key=key, model=model)
                final_prov = p
                final_model = model
                logger.info(f"[LLM Gateway] Success with {p} on attempt {attempt+1}!")
                log_ai_usage(p, model, size_route, False)
                break
            except Exception as e:
                logger.error(f"[LLM Gateway] Attempt {attempt+1} failed for {p} ({model}): {str(e)}")
                last_error = e
                if attempt == 0:
                    await asyncio.sleep(1) # Short wait before retry
                    continue
                else:
                    break # Move to next provider in stack
        
        if answer:
            break

    if answer is None:
        error_detail = f"All LLM providers failed. Last error: {str(last_error)}"
        logger.error(f"[LLM] {error_detail}")
        raise ValueError(error_detail)
    
    # Final validation: ensure answer is not empty
    if isinstance(answer, str) and answer.strip() == "":
        logger.error(f"[LLM] Provider {final_prov} returned empty answer")
        raise ValueError(f"Provider {final_prov} returned an empty response. Please try again.")

    # Save to Cache
    cache_key = get_cache_key(system, messages, final_prov, final_model)
    _RESPONSE_CACHE[cache_key] = answer

    response = {"answer": answer, "chunks": chunks, "provider": final_prov}
    logger.info(f"[LLM] Generate completed successfully - provider: {final_prov}, answer length: {len(answer) if answer else 0}")
    return response



# ── Error handler ────────────────────────────────────────────────────────────

def handle_llm_error(error: Exception, provider: str) -> str:
    err_str = str(error)
    if "401" in err_str or "authentication" in err_str.lower() or "invalid" in err_str.lower():
        return f"❌ **Authentication failed** with {provider}. Please check your API key in Settings."
    if "429" in err_str or "rate" in err_str.lower():
        return f"⏳ **Rate limited** by {provider}. Please wait a moment and try again."
    if "timeout" in err_str.lower():
        return f"⏰ **Request timed out** to {provider}. The model may be overloaded — try again shortly."
    return f"⚠️ **Error from {provider}**: {err_str[:200]}\n\nCheck your API key and try again."
