from fastapi import APIRouter, Cookie, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
import logging
from app.services import llm
from app.services.github import fetch_issue
from app.services.rag import is_indexed, index_repo, get_index_stats
from app.services.github import fetch_all_files
from app.limiter import chat_limiter, index_limiter
from app.models import get_db, User, ConnectedRepository
from app.config import settings
from app.services.admin_state import (
    record_api_key_status,
    record_chat_log,
    record_user_activity,
)
from app.services.user_api_keys import resolve_user_provider_key
from app.middleware import requireUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("prguard")


router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str
    repo: Optional[str] = None
    provider: Optional[str] = "claude"
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
    logger.info(f"[CHAT] Received chat request for repo: {request.repo}")
    user = current_user
    provider = (request.provider or "").strip().lower() or "claude"
    if provider == "gpt4o":
        provider = "gpt"
    resolved_api_key = ""
    
    try:
        # ── RATE LIMIT CHECK ──
        chat_limiter.check("global")
        logger.info(f"[CHAT] Rate limit check passed")

        if not request.repo:
            raise HTTPException(status_code=400, detail="No repo selected.")

        provider, resolved_api_key = await resolve_user_provider_key(
            db,
            user_id=user.id,
            requested_provider=provider,
        )

        stmt = select(ConnectedRepository).where(
            ConnectedRepository.user_id == user.id,
            ConnectedRepository.repo_name == request.repo,
        )
        result = await db.execute(stmt)
        connection = result.scalar_one_or_none()
        if not connection:
            raise HTTPException(
                status_code=403,
                detail="Repository not connected. You must authorize this repository in the dashboard first.",
            )

        logger.info(f"[CHAT] Authentication and repo connection verified")

        # fetch issue details if issue_number provided
        issue = None
        if request.issue_number and gh_token:
            try:
                issue = await fetch_issue(
                    repo=request.repo,
                    issue_number=request.issue_number,
                    token=gh_token,
                )
            except Exception as e:
                logger.warning(f"[CHAT] Could not fetch issue #{request.issue_number}: {str(e)}")
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

        logger.info(f"[CHAT] Repo indexed status: {indexed}")

        record_user_activity(user_id=user.id, username=user.username)
        record_api_key_status(
            user_id=user.id,
            username=user.username,
            provider=provider,
            api_key_present=bool(resolved_api_key),
            validation_result="present",
        )

        logger.info(
            f"[CHAT] Starting LLM generation with {provider or 'default'}..."
        )
        result = await llm.generate(
            question=request.message,
            repo=request.repo,
            history=request.history or [],
            provider=provider,
            api_key=resolved_api_key,
            issue=issue,
            n_chunks=8 if (settings.CHAT_ENABLE_RAG and indexed) else 0,
        )

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

        logger.info(f"Response generated successfully using {provider}")
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

    except ValueError as e:
        logger.warning(f"Validation error in chat: {str(e)}")
        if user:
            record_chat_log(
                user_id=user.id,
                username=user.username,
                repo=request.repo or "",
                provider=provider,
                success=False,
                error=str(e),
            )
        raise HTTPException(status_code=400, detail=str(e))

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
    index_limiter.check("global")

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

        # Index into ChromaDB
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
    stats = get_index_stats(repo)
    return stats


# ── Health check ──────────────────────────────────────────────────────────────


@router.get("/chat/health")
async def chat_health():
    return {"status": "ok", "service": "chat"}
