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


# Custom exception for provider-level failures so callers can map to HTTP errors
class LLMProviderError(Exception):
    pass

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
        "large": "gemini-2.0-flash",
        "small": "gemini-2.0-flash",
    },
}

# ── Token limits & Truncation ────────────────────────────────────────────────
def estimate_tokens(text: str) -> int:
    return len(text) // 4  # rough estimate

def truncate_context(history: list[dict], context: str, max_tokens: int = 4000) -> tuple[list[dict], str]:
    new_history = list(history)
    # Prune history first
    history_tokens = estimate_tokens(json.dumps(new_history))
    while history_tokens > 800 and len(new_history) > 2:
        new_history.pop(0)
        history_tokens = estimate_tokens(json.dumps(new_history))

    # Truncate RAG context if still too large
    context_tokens = estimate_tokens(context)
    if context_tokens > (max_tokens - 1000):
        allowed_chars = (max_tokens - 1000) * 4
        context = context[:allowed_chars] + "\n...[Context truncated]..."
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
        "Senior Engineer. Help developers understand codebases. "
        "Be technical, precise, and extremely concise. "
        "Use markdown. Put code in blocks."
    )

    return "\n\n".join(parts)


# ── Provider-specific callers ────────────────────────────────────────────────
async def _call_claude(system: str, messages: list[dict], api_key: str, model: str, max_tokens: int = 1500) -> str:
    print("USING KEY:", api_key[:10])
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
    print("USING KEY:", api_key[:10])
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


async def _call_gemini(system: str, messages: list[dict], api_key: str, model: str, max_tokens: int = 1024) -> str:
    print("USING KEY:", api_key[:10])
    if not api_key:
        raise ValueError("Gemini API key is missing or empty")
    
    url = PROVIDERS["gemini"]["url"].format(model=model)
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    contents = []
    # Prepend system instruction to the first message for maximum compatibility across v1/v1beta
    first_msg = True
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        text = msg["content"]
        if first_msg and role == "user":
            text = f"{system}\n\n{text}"
            first_msg = False
        contents.append({"role": role, "parts": [{"text": text}]})
    
    body = {
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
        data = {"error": {"message": resp.text[:1000] or "Non-JSON response from Gemini"}}
    
    if resp.status_code != 200 or "error" in data:
        error_data = data.get("error", {})
        if isinstance(error_data, dict):
            detail = error_data.get("message", str(data))
        else:
            detail = str(error_data)
        
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


def _provider_model_candidates(provider: str, size_route: str, requested_model: Optional[str] = None) -> list[str]:
    if provider == "gemini":
        return settings.gemini_model_candidates(requested_model=requested_model)

    candidates: list[str] = []
    if requested_model:
        candidates.append(requested_model)

    default_model = PROVIDERS[provider][size_route]
    if default_model not in candidates:
        candidates.append(default_model)

    return candidates

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

async def generate(question: str, repo: str, history: list[dict], provider: str = "claude", api_key: str | dict[str, str] = "", issue: Optional[dict] = None, n_chunks: int = 8, extra_context: Optional[str] = None, model: Optional[str] = None) -> dict:
    # ── 1. Validate API keys BEFORE doing expensive RAG ──────────────────────
    stack = _resolve_provider_stack(provider)
    valid_keys = {}
    
    # Log API key debug info
    print(f"[LLM] -- Generate Request --")
    print(f"[LLM] PROVIDER SELECTED: {provider}")
    print(f"[LLM] Provider fallback stack: {stack}")
    print(f"[LLM] Request API key provided: {'yes' if api_key else 'no'}")
    print(f"[LLM] Requested model: {model or 'auto'}")
    print(f"[LLM] RAG chunks requested: {n_chunks}")
    
    user_keys = api_key if isinstance(api_key, dict) else {stack[0]: api_key} if api_key else {}

    for p in stack:
        # Multi-user safety: Priority 1 is the key provided in the request
        k = user_keys.get(p)
        
        # Priority 2: Fallback to environment keys if in development
        if not k and settings.ENVIRONMENT == "development":
            k = _get_fallback_key(p)
            
        if k:
            valid_keys[p] = k
            print("LLM USING KEY:", k[:10], "provider:", p)
            logger.info(f"[LLM] Key available for {p}")
        else:
            print(f"[LLM] No key available for {p}")
            logger.info(f"[LLM] No key available for {p}")

    if not valid_keys:
        error_detail = (
            "No LLM API keys found. Please provide an API key in 'Settings' "
            "or set OPENAI_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY in your .env file."
        )
        logger.error(f"[LLM] {error_detail}")
        raise ValueError(error_detail)

    # ── 2. RAG Retrieval ─────────────────────────────────────────────────────
    chunks = []
    if n_chunks > 0:
        try:
            chunks = await retrieve(repo=repo, query=question, n_results=n_chunks)
            print(f"[LLM] RAG retrieval returned {len(chunks)} chunks")
        except Exception as rag_err:
            logger.warning(f"[LLM] RAG retrieval failed (continuing without context): {rag_err}")
            print(f"[LLM] RAG retrieval FAILED: {rag_err}")
            chunks = []

    raw_context = format_chunks_for_prompt(chunks)
    if extra_context:
        raw_context = f"{extra_context}\n\n{raw_context}" if raw_context and raw_context != "No relevant code found." else extra_context

    # ── 3. Token Limits & History Truncation ─────────────────────────────────
    history, context = truncate_context(history, raw_context, max_tokens=15000)
    system = _build_system_prompt(repo=repo, issue=issue, context=context)
    messages = history + [{"role": "user", "content": question}]

    # Determine "Model Size" routing
    # For small, fast queries (e.g. general chat), use "small" model. 
    # For large contexts (e.g. full visualization), use "large" model.
    size_route = "large" if estimate_tokens(context) > 2000 or issue else "small"
    print(f"[LLM] Size route: {size_route}, context tokens ~{estimate_tokens(context)}")

    # ── 4. Cache Check ───────────────────────────────────────────────────────
    answer = None
    final_prov = stack[0]
    requested_model = model  # preserve the original requested model
    final_model = model or PROVIDERS[final_prov][size_route]

    for provider_candidate in stack:
        for model_candidate in _provider_model_candidates(provider_candidate, size_route, requested_model if provider_candidate == provider else None):
            cache_key = get_cache_key(system, messages, provider_candidate, model_candidate)
            if cache_key in _RESPONSE_CACHE:
                print(f"[LLM] Cache HIT for {provider_candidate} ({model_candidate})")
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
    backoffs = [1, 2, 4]

    for p in stack:
        if p not in valid_keys:
            print(f"[LLM] SKIPPING provider {p} (no key)")
            continue
        attempted.append(p)
        key = valid_keys[p]
        caller = _CALLERS[p]

        # Build model fallback list for this provider. Gemini gets explicit
        # free-tier-friendly fallback candidates from settings.
        models_to_try = _provider_model_candidates(p, size_route, requested_model if p == provider else None)
        if p != "gemini" and size_route == "large":
            # Prefer large, but allow fallback to small on retryable failures.
            small_model = PROVIDERS[p]["small"]
            if small_model not in models_to_try:
                models_to_try.append(small_model)

        print(f"[LLM] Trying provider: {p}, models: {models_to_try}")
        print(f"[LLM] USING KEY: {key[:10]}...")

        for model_name in models_to_try:
            # Try the model, with initial attempt + len(backoffs) retries
            for attempt in range(len(backoffs) + 1):
                try:
                    print(f"[LLM Gateway] Attempt {attempt+1} for {p} ({model_name})...")
                    logger.info(f"[LLM Gateway] Attempt {attempt+1} for {p} ({model_name})...")
                    answer = await caller(system=system, messages=messages, api_key=key, model=model_name)
                    final_prov = p
                    final_model = model_name
                    print(f"[LLM Gateway] [OK] SUCCESS with {p} ({model_name}) on attempt {attempt+1}")
                    logger.info(f"[LLM Gateway] Success with {p} on attempt {attempt+1}!")
                    log_ai_usage(p, model_name, size_route, False)
                    break
                except Exception as e:
                    last_error = e
                    err_str = str(e).lower()
                    print(f"[LLM Gateway] [FAIL] attempt {attempt+1} for {p} ({model_name}): {str(e)}")
                    logger.error(f"[LLM Gateway] Attempt {attempt+1} failed for {p} ({model_name}): {str(e)}")

                    # Fatal errors should not be retried (auth issues, invalid request)
                    if "401" in err_str or "authentication" in err_str or ("invalid" in err_str and "api" in err_str):
                        print(f"[LLM Gateway] FATAL error for {p} ({model_name}), not retrying")
                        logger.error(f"[LLM Gateway] Fatal error for {p} ({model_name}): {err_str}")
                        break

                    # Retryable errors: 429/503/rate/timeout/quota/service unavailable
                    is_retryable = any(tok in err_str for tok in ("429", "503", "rate", "timeout", "quota", "service unavailable"))

                    # If we can retry this model, wait and retry. Otherwise, move to next model/provider.
                    if is_retryable and attempt < len(backoffs):
                        wait_time = backoffs[attempt]
                        print(f"[LLM Gateway] FALLBACK: Waiting {wait_time}s before retry for {p} ({model_name})...")
                        logger.warning(f"[LLM Gateway] Waiting {wait_time}s before retry {attempt+1} for {p} ({model_name})...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        print(f"[LLM Gateway] FALLBACK: Moving to next model/provider after {p} ({model_name}) failure")
                        # No more retries for this model
                        break

            if answer:
                break
        
        if answer:
            break

    if answer is None:
        error_detail = f"All LLM providers failed. Attempted: {attempted}. Last error: {str(last_error)}"
        print(f"[LLM] [FAIL] {error_detail}")
        logger.error(f"[LLM] {error_detail}")
        raise LLMProviderError(error_detail)
    
    # Final validation: ensure answer is not empty
    if isinstance(answer, str) and answer.strip() == "":
        print(f"[LLM] [FAIL] Provider {final_prov} returned empty answer")
        logger.error(f"[LLM] Provider {final_prov} returned empty answer")
        raise LLMProviderError(f"Provider {final_prov} returned an empty response. Please try again.")

    # Save to Cache
    cache_key = get_cache_key(system, messages, final_prov, final_model)
    _RESPONSE_CACHE[cache_key] = answer

    response = {"answer": answer, "chunks": chunks, "provider": final_prov}
    print(f"[LLM] [OK] Generate completed - provider: {final_prov}, model: {final_model}, answer length: {len(answer)}")
    logger.info(f"[LLM] Generate completed successfully - provider: {final_prov}, answer length: {len(answer) if answer else 0}")
    return response



# ── Error handler ────────────────────────────────────────────────────────────

def handle_llm_error(error: Exception, provider: str) -> str:
    err_str = str(error)
    if "401" in err_str or "authentication" in err_str.lower() or "invalid" in err_str.lower():
        return f"[AUTH ERROR] Authentication failed with {provider}. Please check your API key in Settings."
    if "429" in err_str or "rate" in err_str.lower():
        return f"[RATE LIMITED] Rate limited by {provider}. Please wait a moment and try again."
    if "timeout" in err_str.lower():
        return f"[TIMEOUT] Request timed out to {provider}. The model may be overloaded - try again shortly."
    return f"[!] Error from {provider}: {err_str[:200]}\n\nCheck your API key and try again."
