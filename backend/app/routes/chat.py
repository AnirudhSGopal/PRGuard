import re

from fastapi import APIRouter, Cookie, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
import logging
from app.services import llm
from app.services.llm import LLMProviderError
from app.services.github import fetch_issue
from app.services.rag import (
    is_indexed,
    index_repo,
    get_index_stats,
    get_file_chunks,
    get_file_references,
    format_file_explanation_context,
)
from app.services.github import fetch_all_files
from app.limiter import chat_limiter, index_limiter
from app.models import get_db, User, ConnectedRepository
from app.config import settings
from app.services.admin_state import (
    record_api_key_status,
    record_chat_log,
    record_user_activity,
)
from app.services.user_api_keys import resolve_user_provider_keys
from app.middleware import requireUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("prguard")


router = APIRouter()


FILE_EXPLANATION_RE = re.compile(r"^\s*explain(?:\s+the)?\s+file\s*:?(?P<path>.+?)\s*$", re.IGNORECASE)


def _extract_file_path(message: str) -> str | None:
    match = FILE_EXPLANATION_RE.match(message or "")
    if not match:
        return None
    path = match.group("path").strip().strip('"').strip("'").strip("`")
    return path or None


def _is_provider_retryable_error(error_text: str) -> bool:
    lower_error = (error_text or "").lower()
    return any(
        token in lower_error
        for token in (
            "429",
            "503",
            "quota",
            "rate limit",
            "rate limited",
            "too many requests",
            "authentication",
            "unauthorized",
            "forbidden",
            "not valid",
            "invalid api key",
            "http request failed",
            "service unavailable",
            "high demand",
            "overloaded",
        )
    )


# ── Request / Response models ─────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str
    repo: Optional[str] = None
    provider: Optional[str] = "claude"
    model: Optional[str] = None
    issue_number: Optional[int] = None
    history: list[dict] = Field(default_factory=list)


class Source(BaseModel):
    file: str
    lines: str
    relevance: float


class ChatResponse(BaseModel):
    message: str
    answer: str
    sources: list[Source] = Field(default_factory=list)
    provider: str = "claude"
    indexed: bool = False


class IndexRequest(BaseModel):
    repo: str


class IndexResponse(BaseModel):
    repo: str
    files: int
    chunks: int
    indexed: bool


# ── Chat endpoint ─────────────────────────────────────────────────────────────


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(requireUser),
    gh_token: str = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Main chat endpoint.
    Connects frontend ChatPanel to RAG + LLM pipeline.
    """
    print("=" * 60)
    print(f"[CHAT] -- New Chat Request --")
    print(f"[CHAT] User: {current_user.username} ({current_user.id})")
    print(f"[CHAT] Repo: {request.repo}")
    print(f"[CHAT] Provider (requested): {request.provider}")
    print(f"[CHAT] Model (requested): {request.model or 'auto'}")
    print(f"[CHAT] Message: {request.message[:100]}{'...' if len(request.message) > 100 else ''}")
    print(f"[CHAT] History length: {len(request.history)}")
    print(f"[CHAT] Issue number: {request.issue_number}")
    print("=" * 60)

    logger.info(f"[CHAT] Received chat request for repo: {request.repo}")
    user = current_user
    file_explanation_path = _extract_file_path(request.message)
    provider = (request.provider or "").strip().lower() or "claude"
    if provider == "gpt4o":
        provider = "gpt"
    resolved_api_key = ""
    
    try:
        # ── RATE LIMIT CHECK ──
        print(f"[CHAT] Step 1: Rate limit check for user {user.id}...")
        chat_limiter.check(str(user.id))
        print(f"[CHAT] Step 1: [OK] Rate limit passed")

        if not request.repo:
            raise HTTPException(status_code=400, detail="No repo selected.")

        # ── RESOLVE PROVIDER KEYS ──
        print(f"[CHAT] Step 2: Resolving provider keys for '{provider}'...")
        provider_candidates = await resolve_user_provider_keys(
            db,
            user_id=user.id,
            requested_provider=provider,
        )
        print(f"[CHAT] Step 2: [OK] Candidates resolved: {[(p[0], p[1][:10] + '...') for p in provider_candidates]}")

        if not provider_candidates:
            raise HTTPException(
                status_code=400,
                detail="No API key configured. Add one in Settings and try again.",
            )

        provider, resolved_api_key = provider_candidates[0]
        print(f"[CHAT] Step 2: Primary provider: {provider}, key: {resolved_api_key[:10]}...")

        # ── REPO CONNECTION CHECK ──
        print(f"[CHAT] Step 3: Checking repo connection for '{request.repo}'...")
        stmt = select(ConnectedRepository).where(
            ConnectedRepository.user_id == user.id,
            ConnectedRepository.repo_name == request.repo,
        )
        result = await db.execute(stmt)
        connection = result.scalar_one_or_none()
        if not connection:
            print(f"[CHAT] Step 3: [FAIL] Repo not connected!")
            raise HTTPException(
                status_code=403,
                detail="Repository not connected. You must authorize this repository in the dashboard first.",
            )
        print(f"[CHAT] Step 3: [OK] Repo connection verified")


        # ── API KEY VALIDATION ──
        print(f"[CHAT] Step 4: Validating API key...")
        if not resolved_api_key or not resolved_api_key.strip():
            print(f"[CHAT] Step 4: [FAIL] No API key for {provider}!")
            raise HTTPException(
                status_code=400,
                detail=f"No API key configured for {provider}. Please add an API key in Settings and try again."
            )
        print(f"[CHAT] Step 4: [OK] API key valid ({resolved_api_key[:10]}...)")

        # fetch issue details if issue_number provided
        issue = None
        if request.issue_number and gh_token:
            try:
                issue = await fetch_issue(
                    repo=request.repo,
                    issue_number=request.issue_number,
                    token=gh_token,
                )
                print(f"[CHAT] Step 5: [OK] Issue #{request.issue_number} fetched")
            except Exception as e:
                print(f"[CHAT] Step 5: [WARN] Could not fetch issue #{request.issue_number}: {e}")
                issue = None  # Continue without issue context

        # check if repo is indexed
        # RAG can be disabled for chat stability in development.
        indexed = False
        if settings.CHAT_ENABLE_RAG:
            try:
                if request.repo:
                    indexed = await is_indexed(request.repo)
            except Exception as e:
                logger.warning(f"[CHAT] Could not check indexed status: {str(e)}")
                indexed = False  # Continue without indexing info

        rag_chunks_to_use = 5 if (settings.CHAT_ENABLE_RAG and indexed) else 0
        print(f"[CHAT] Step 5: RAG enabled={settings.CHAT_ENABLE_RAG}, indexed={indexed}, chunks={rag_chunks_to_use}")

        file_explanation_context = None
        if file_explanation_path:
            file_chunks = await get_file_chunks(request.repo, file_explanation_path)
            if not file_chunks:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"File '{file_explanation_path}' could not be found in the repository index. "
                        f"Index the repository first, then try again."
                    ),
                )
            file_references = await get_file_references(request.repo, file_explanation_path)
            file_explanation_context = format_file_explanation_context(
                file_explanation_path,
                file_chunks,
                file_references,
            )

        record_user_activity(user_id=user.id, username=user.username)
        record_api_key_status(
            user_id=user.id,
            username=user.username,
            provider=provider,
            api_key_present=bool(resolved_api_key),
            validation_result="present",
        )

        # ── LLM GENERATION ──
        print(f"[CHAT] Step 6: Starting LLM generation...")
        result = None
        last_error = None
        for candidate_provider, candidate_key in provider_candidates:
            print(f"[CHAT] Step 6: Trying {candidate_provider} (key: {candidate_key[:10]}...)")
            try:
                # Trim history to last 6 messages (3 turns) to save tokens
                trimmed_history = (request.history or [])[-6:]
                
                result = await llm.generate(
                    question=request.message,
                    repo=request.repo,
                    history=trimmed_history,
                    provider=candidate_provider,
                    api_key=candidate_key,
                    issue=issue,
                    n_chunks=rag_chunks_to_use,
                    extra_context=file_explanation_context,
                    model=request.model,
                )
                print(f"[CHAT] Step 6: [OK] LLM generation succeeded with {candidate_provider}")
                provider = result.get("provider", candidate_provider)
                resolved_api_key = candidate_key
                break
            except Exception as e:
                print(f"[CHAT] Step 6: [FAIL] LLM failed for {candidate_provider}: {str(e)[:200]}")
                last_error = e
                error_text = str(e)
                logger.error(f"[CHAT] llm.generate failed for {candidate_provider}: {error_text}")
                if not _is_provider_retryable_error(error_text):
                    raise

        
        if result is None:
            err = str(last_error) if last_error else "LLM service returned no result"
            print(f"[CHAT] Step 6: [FAIL] ALL providers failed! Last error: {err[:200]}")
            logger.error(f"LLM call failed: {err}")
            if user:
                record_chat_log(
                    user_id=user.id,
                    username=user.username,
                    repo=request.repo or "",
                    provider=provider,
                    success=False,
                    error=err,
                )
            # Raise as ValueError so the exception handler can parse the string
            # and map it to 400 (auth) or 503 (rate limit) correctly.
            raise ValueError(err)

        # Validate result structure
        if not result:
            raise ValueError("LLM service returned empty result")
        
        answer = result.get("answer", "")
        if not isinstance(answer, str):
            answer = str(answer or "")
        
        if not answer or answer.strip() == "":
            raise ValueError("LLM service returned empty answer")
        
        provider = result.get("provider", provider)
        chunks = result.get("chunks", [])
        
        # format sources for frontend
        sources = []
        try:
            for chunk in chunks[:5]:  # top 5 sources
                if isinstance(chunk, dict):
                    sources.append(
                        Source(
                            file=chunk.get("path", "unknown"),
                            lines=f"{chunk.get('start_line', 0)}-{chunk.get('end_line', 0)}",
                            relevance=float(chunk.get("similarity", 0.0))
                        )
                    )
        except Exception as e:
            logger.warning(f"[CHAT] Could not format sources: {str(e)}")
            sources = []  # Continue without sources

        print(f"[CHAT] Step 7: [OK] Response ready")
        print(f"[CHAT]   Provider: {provider}")
        print(f"[CHAT]   Answer length: {len(answer)} chars")
        print(f"[CHAT]   Sources: {len(sources)}")
        print(f"[CHAT]   RAG indexed: {indexed}")
        print("=" * 60)

        record_chat_log(
            user_id=user.id,
            username=user.username,
            repo=request.repo,
            provider=provider,
            success=True,
        )

        return ChatResponse(
            message=answer,
            answer=answer,
            sources=sources,
            provider=provider,
            indexed=indexed,
        )

    except (ValueError, LLMProviderError) as e:
        error_text = str(e)
        logger.warning(f"Validation or provider error in chat: {error_text}")
        if user:
            record_chat_log(
                user_id=user.id,
                username=user.username,
                repo=request.repo or "",
                provider=provider,
                success=False,
                error=error_text,
            )
        lower_error = error_text.lower()
        if (
            "api key" in lower_error
            or "authentication" in lower_error
            or "unauthorized" in lower_error
            or "forbidden" in lower_error
            or "not valid" in lower_error
            or "pass a valid api key" in lower_error
            or ("invalid" in lower_error and "api" in lower_error)
        ):
            raise HTTPException(status_code=400, detail=error_text)
        # Handle provider rate limits and quota issues as upstream unavailability.
        if (
            "429" in lower_error
            or "quota" in lower_error
            or "rate limit" in lower_error
            or "rate limited" in lower_error
            or "too many requests" in lower_error
        ):
            raise HTTPException(
                status_code=503,
                detail=error_text,
            )
        if "503" in lower_error or "high demand" in lower_error or "service unavailable" in lower_error or "overloaded" in lower_error:
            raise HTTPException(status_code=503, detail=error_text)
        # Only map to 502 if it's truly a gateway/connectivity issue
        if ("api error" in lower_error and "returned empty response" in lower_error) or "http request failed" in lower_error or "timeout" in lower_error:
            raise HTTPException(status_code=502, detail=error_text)
            
        if isinstance(e, LLMProviderError):
            raise HTTPException(status_code=503, detail=error_text)
        raise HTTPException(status_code=400, detail=error_text)

    except HTTPException:
        if user:
            record_chat_log(
                user_id=user.id,
                username=user.username,
                repo=request.repo or "",
                provider=provider,
                success=False,
                error="HTTP error",
            )
        raise  # Re-raise HTTP exceptions as-is
    
    
    except Exception as e:
        logger.error(f"LLM Error in chat endpoint: {str(e)}", exc_info=True)
        if user:
            record_chat_log(
                user_id=user.id,
                username=user.username,
                repo=request.repo or "",
                provider=provider,
                success=False,
                error=str(e),
            )
        error_msg = llm.handle_llm_error(e, request.provider or "claude")
        raise HTTPException(
            status_code=500,
            detail=error_msg
            or "An unexpected error occurred while communicating with the AI.",
        )


# ── Index endpoint ────────────────────────────────────────────────────────────


@router.post("/index", response_model=IndexResponse)
async def index_repository(
    request: IndexRequest,
    current_user: User = Depends(requireUser),
    gh_token: str = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    # ── RATE LIMIT CHECK ──
    index_limiter.check(str(current_user.id))

    # ── OPENAI_API_KEY CHECK ──
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=400,
            detail="RAG indexing requires OPENAI_API_KEY. "
                   "Please add it to your environment variables.",
        )

    user = current_user

    stmt = select(ConnectedRepository).where(
        ConnectedRepository.user_id == user.id,
        ConnectedRepository.repo_name == request.repo,
    )
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: Repository not connected in dashboard",
        )

    logger.debug(f"Indexing request for {request.repo}")
    logger.debug(f"gh_token cookie present: {'YES' if gh_token else 'NO'}")

    # 🌐 Public repos work without auth (60 req/hr GitHub rate limit).
    # Only private repos strictly need a gh_token.
    # We pass the token if available to get higher rate limits + private repo access.

    try:
        # fetch all files from GitHub (token can be None for public repos)
        files = await fetch_all_files(
            repo=request.repo,
            token=gh_token or "",
        )
        if not files:
            raise HTTPException(
                status_code=404,
                detail=f"No source files found in '{request.repo}'. Check the repo name or ensure it has supported source files.",
            )

        # Index into the vector store
        result = await index_repo(
            repo=request.repo,
            files=files,
        )

        return IndexResponse(
            repo=request.repo,
            files=len(files),
            chunks=result.get("chunks", 0),
            indexed=True,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Indexing failed for {request.repo}: {e}", exc_info=True)
        error_detail = str(e)
        if "404" in error_detail or "not found" in error_detail.lower():
            error_detail = (
                f"Repository '{request.repo}' not found. Check the owner/repo name."
            )
        elif "401" in error_detail or "403" in error_detail:
            error_detail = "GitHub auth failed. If this is a private repo, please log in with GitHub first."
        elif "rate limit" in error_detail.lower():
            error_detail = "GitHub API rate limit reached. Log in with GitHub to get higher limits."

        raise HTTPException(status_code=400, detail=error_detail)


# ── Index status endpoint ─────────────────────────────────────────────────────


@router.get("/index/status")
async def index_status(repo: str):
    """
    Check if a repo is indexed and how many chunks it has.
    Called by frontend to show indexed/not indexed badge.
    """
    stats = await get_index_stats(repo)
    return stats


# ── Health check ──────────────────────────────────────────────────────────────


@router.get("/chat/health")
async def chat_health():
    return {"status": "ok", "service": "chat"}
