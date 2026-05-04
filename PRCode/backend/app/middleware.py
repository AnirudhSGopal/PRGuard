import time
import logging
import uuid
from sqlalchemy import select
from fastapi import Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.models.base import AsyncSessionLocal
from app.models import get_db
from app.models.user import User
from app.services.admin_auth import hash_session_token
from app.services.auth_session import ADMIN_SESSION_COOKIE_NAME, USER_SESSION_COOKIE_NAME

logger = logging.getLogger("prguard")

class GlobalHardenMiddleware(BaseHTTPMiddleware):
    """
    Principal Engineer's Hardening Middleware:
    1. Global request logging (method, path, duration)
    2. Centralized error handling (no more silent 500s)
    3. Resilience against unhandled exceptions
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        
        try:
            # 1. Process request
            response = await call_next(request)
            
            # 2. Log success
            process_time = time.time() - start_time
            logger.info(
                f"{request.method} {request.url.path} "
                f"status={response.status_code} "
                f"time={process_time:.3f}s"
            )
            return response

        except Exception as e:
            # 3. Handle failure
            process_time = time.time() - start_time
            error_id = str(uuid.uuid4())
            logger.exception(
                f"CRITICAL ERROR [{error_id}] {request.method} {request.url.path} "
                f"time={process_time:.3f}s"
            )
            
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "An internal server error occurred.",
                    "error_id": error_id,
                }
            )


class AdminRoleMiddleware(BaseHTTPMiddleware):
    """Enforce backend admin authorization for all protected /admin routes."""

    _open_admin_paths = {
        "/admin/login",
        "/admin/me",
    }

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if not path.startswith("/admin"):
            return await call_next(request)

        logger.info("admin_middleware_enter path=%s method=%s", path, request.method)

        if request.method == "OPTIONS" or path in self._open_admin_paths:
            logger.info("admin_middleware_bypass path=%s reason=open_or_options", path)
            return await call_next(request)

        raw_token = (request.cookies.get(ADMIN_SESSION_COOKIE_NAME) or "").strip()
        if not raw_token:
            logger.info("admin_middleware_reject path=%s reason=missing_session_token", path)
            return JSONResponse(status_code=401, content={"detail": "Admin authentication required"})

        token_hash = hash_session_token(raw_token)
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(
                User.session_token_hash == token_hash,
                User.role == "admin",
                User.auth_provider == "local",
                User.is_disabled.is_(False),
            )
            result = await session.execute(stmt)
            admin_user = result.scalar_one_or_none()

        if not admin_user:
            logger.info("admin_middleware_reject path=%s reason=session_not_admin", path)
            return JSONResponse(status_code=403, content={"detail": "Admin access required"})

        request.state.admin_user_id = admin_user.id
        request.state.admin_username = admin_user.username
        logger.info("admin_middleware_allow path=%s admin_user_id=%s", path, admin_user.id)
        return await call_next(request)


async def requireAuth(
    session_token: str | None = Cookie(default=None, alias=USER_SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> User:
    raw_token = (session_token or "").strip()
    if not raw_token:
        raise HTTPException(status_code=401, detail="Authentication required")

    stmt = select(User).where(
        User.session_token_hash == hash_session_token(raw_token),
        User.is_disabled.is_(False),
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


async def get_current_user(
    user_token: str | None = Cookie(default=None, alias=USER_SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> User:
    raw_token = (user_token or "").strip()
    if not raw_token:
        raise HTTPException(status_code=401, detail="User authentication required")

    stmt = select(User).where(
        User.session_token_hash == hash_session_token(raw_token),
        User.role == "user",
        User.auth_provider == "github",
        User.is_disabled.is_(False),
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired user session")
    return user


async def get_current_admin(
    admin_token: str | None = Cookie(default=None, alias=ADMIN_SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> User:
    raw_token = (admin_token or "").strip()
    if not raw_token:
        raise HTTPException(status_code=401, detail="Admin authentication required")

    stmt = select(User).where(
        User.session_token_hash == hash_session_token(raw_token),
        User.role == "admin",
        User.auth_provider == "local",
        User.is_disabled.is_(False),
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired admin session")
    return user


async def requireUser(current_user: User = Depends(get_current_user)) -> User:
    if (current_user.role or "").strip().lower() != "user":
        raise HTTPException(status_code=403, detail="User access required")
    if (current_user.auth_provider or "").strip().lower() != "github":
        raise HTTPException(status_code=403, detail="GitHub login required")
    return current_user


async def requireAdmin(current_user: User = Depends(get_current_admin)) -> User:
    if (current_user.role or "").strip().lower() != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    if (current_user.auth_provider or "").strip().lower() != "local":
        raise HTTPException(status_code=403, detail="Local admin login required")
    return current_user


async def admin_required(current_user: User = Depends(requireAdmin)) -> User:
    return current_user
