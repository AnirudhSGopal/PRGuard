import logging
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, get_db
from app.middleware import requireUser
from app.services import llm, github, rag
from app.limiter import chat_limiter, index_limiter

router = APIRouter()
logger = logging.getLogger("prguard")

class ChatMessage(BaseModel):
    role: str
    content: str
    isError: Optional[bool] = False

class ChatRequest(BaseModel):
    message: str
    repo: str
    provider: Optional[str] = "gemini"
    issue_number: Optional[int] = None
    history: Optional[List[ChatMessage]] = []

@router.post("/chat")
async def chat_endpoint(
    request: Request,
    payload: ChatRequest,
    user: User = Depends(requireUser),
    db: AsyncSession = Depends(get_db)
):
    # Enforce per-IP rate limiting
    chat_limiter.check(request.client.host)
    
    logger.info(f"Chat request from user {user.id} for repo {payload.repo}")
    
    try:
        # Context building
        context = ""
        if payload.issue_number:
            issue = await github.get_issue(payload.repo, payload.issue_number, user.access_token)
            context += f"Context: Reviewing Issue #{payload.issue_number}: {issue.get('title')}\n{issue.get('body')}\n\n"
        
        # RAG search if enabled
        if settings.CHAT_ENABLE_RAG:
            relevant_chunks = await rag.search(payload.repo, payload.message)
            if relevant_chunks:
                context += "Relevant Code Context:\n" + "\n".join(relevant_chunks) + "\n\n"

        response = await llm.generate(
            prompt=payload.message,
            context=context,
            history=payload.history,
            provider=payload.provider,
            user_id=user.id,
            db=db
        )
        return {"message": response}
    except Exception as e:
        logger.error(f"Chat failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate response")

@router.post("/index")
async def index_repo(
    request: Request,
    payload: dict,
    user: User = Depends(requireUser)
):
    # Heavy operation, strict limit
    index_limiter.check(request.client.host)
    
    repo = payload.get("repo")
    if not repo:
        raise HTTPException(status_code=400, detail="Repo name is required")
        
    logger.info(f"Indexing request for {repo} by user {user.id}")
    try:
        result = await rag.index_repository(repo, user.access_token)
        return result
    except Exception as e:
        logger.error(f"Indexing failed for {repo}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")

@router.get("/index/status")
async def get_index_status(
    repo: str,
    user: User = Depends(requireUser)
):
    # Route was previously unprotected, now requires user session
    status = await rag.get_index_status(repo)
    return status
