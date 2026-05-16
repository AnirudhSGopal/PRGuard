import logging
import uuid
import time
from datetime import datetime, timezone
from fastapi import Request, HTTPException, Depends, Cookie
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import get_db, User
from app.services.auth_session import (
    USER_SESSION_COOKIE_NAME,
    ADMIN_SESSION_COOKIE_NAME,
    get_user_from_user_session,
    get_user_from_admin_session,
)

logger = logging.getLogger("prguard")

# ── Global Harden Middleware ──────────────────────────────────────────────────
class GlobalHardenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            error_id = str(uuid.uuid4())
            logger.error(f"Unhandled Exception [ID: {error_id}]: {str(e)}", exc_info=True)
            
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "An internal server error occurred. Our team has been notified.",
                    "error_id": error_id
                }
            )

# ── Authentication Dependencies ───────────────────────────────────────────────

async def requireUser(
    user_token: str | None = Cookie(default=None, alias=USER_SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db)
) -> User:
    if not user_token:
        raise HTTPException(status_code=401, detail="Session missing")
    
    user = await get_user_from_user_session(db, user_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    if user.is_disabled:
        raise HTTPException(status_code=403, detail="Account disabled")
    
    # Check session expiry
    if user.expires_at:
        # Normalize to UTC for comparison
        expires_at = user.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
            
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
            
    return user

async def admin_required(
    admin_token: str | None = Cookie(default=None, alias=ADMIN_SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db)
) -> User:
    if not admin_token:
        raise HTTPException(status_code=401, detail="Admin session missing")
    
    user = await get_user_from_admin_session(db, admin_token)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    
    if user.is_disabled:
        raise HTTPException(status_code=403, detail="Account disabled")

    # Check session expiry
    if user.expires_at:
        expires_at = user.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
            
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
            
    return user

# ── Role Middleware (Legacy) ──────────────────────────────────────────────────
class AdminRoleMiddleware(BaseHTTPMiddleware):
    """Verifies admin session for /admin routes."""
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/admin") and request.url.path not in ["/admin/login", "/admin/logout"]:
            # This is a bit complex for middleware since we need DB access
            # Recommended: Use Dependencies in routes instead (admin_required)
            pass
        return await call_next(request)
