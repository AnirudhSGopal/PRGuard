from __future__ import annotations

from datetime import datetime, timezone
import logging

from fastapi import HTTPException, Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User
from app.services.admin_auth import create_session_token, hash_session_token, verify_password

USER_SESSION_COOKIE_NAME = "user_token"
ADMIN_SESSION_COOKIE_NAME = "admin_token"

logger = logging.getLogger("prguard")


async def _recover_default_admin_if_configured(
    db: AsyncSession,
    identifier: str,
    password: str,
) -> User | None:
    configured_username = (settings.ADMIN_USERNAME or "").strip().lower()
    configured_email = (settings.ADMIN_EMAIL or "").strip().lower()
    configured_password = (settings.ADMIN_PASSWORD or "").strip()

    matches_identifier = identifier and identifier in {configured_username, configured_email}
    if not matches_identifier or not configured_password or password != configured_password:
        return None

    # Auto-repair stale/missing admin rows using configured local admin credentials.
    from app.services.admin_bootstrap import ensure_default_admin

    await ensure_default_admin(db)

    stmt = select(User).where(
        or_(
            func.lower(User.email) == identifier,
            func.lower(User.username) == identifier,
        ),
        User.role == "admin",
        User.auth_provider == "local",
        User.is_disabled.is_(False),
    ).order_by(User.created_at.desc()).limit(1)
    result = await db.execute(stmt)
    return result.scalars().first()


async def authenticate_admin_credentials(
    db: AsyncSession,
    email: str,
    password: str,
) -> User:
    identifier = (email or "").strip().lower()
    if not identifier or not password:
        logger.warning("admin_login_attempt rejected: missing_email_or_password")
        raise HTTPException(status_code=400, detail="Email and password are required")

    logger.info("admin_login_attempt started identifier=%s", identifier)

    stmt = select(User).where(
        or_(
            func.lower(User.email) == identifier,
            func.lower(User.username) == identifier,
        ),
        User.role == "admin",
        User.auth_provider == "local",
        User.is_disabled.is_(False),
    ).order_by(User.created_at.desc()).limit(1)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        recovered = await _recover_default_admin_if_configured(db, identifier=identifier, password=password)
        if recovered:
            logger.info("admin_login_attempt recovered_via_bootstrap user_id=%s", recovered.id)
            return recovered
        logger.warning("admin_login_attempt denied identifier=%s reason=role_or_provider_mismatch", identifier)
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    if user.github_id:
        logger.warning("admin_login_attempt denied user_id=%s reason=github_linked_admin", user.id)
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    if not verify_password(password, user.password_hash or ""):
        recovered = await _recover_default_admin_if_configured(db, identifier=identifier, password=password)
        if recovered:
            logger.info("admin_login_attempt recovered_after_password_mismatch user_id=%s", recovered.id)
            return recovered
        logger.warning("admin_login_attempt denied user_id=%s reason=invalid_password", user.id)
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    logger.info("admin_login_attempt succeeded user_id=%s identifier=%s", user.id, identifier)
    return user


def _set_cookie(response: Response, cookie_name: str, session_token: str) -> None:
    is_prod = settings.ENVIRONMENT == "production"
    response.set_cookie(
        key=cookie_name,
        value=session_token,
        httponly=True,
        secure=is_prod,
        samesite="none" if is_prod else "lax",
        max_age=settings.ADMIN_SESSION_TTL_SECONDS,
        path="/",
    )


def _clear_cookie(response: Response, cookie_name: str) -> None:
    is_prod = settings.ENVIRONMENT == "production"
    response.delete_cookie(
        key=cookie_name,
        path="/",
        httponly=True,
        samesite="none" if is_prod else "lax",
        secure=is_prod,
    )


def issue_user_session(user: User, response: Response) -> str:
    session_token = create_session_token()
    user.session_token_hash = hash_session_token(session_token)
    user.last_login_at = datetime.now(timezone.utc)
    _set_cookie(response, USER_SESSION_COOKIE_NAME, session_token)
    logger.info("user_session_issued user_id=%s auth_provider=%s", user.id, user.auth_provider)
    return session_token


def issue_admin_session(user: User, response: Response) -> str:
    session_token = create_session_token()
    user.session_token_hash = hash_session_token(session_token)
    user.last_login_at = datetime.now(timezone.utc)
    _set_cookie(response, ADMIN_SESSION_COOKIE_NAME, session_token)
    logger.info("admin_session_issued user_id=%s auth_provider=%s", user.id, user.auth_provider)
    return session_token


def clear_user_session_cookie(response: Response) -> None:
    _clear_cookie(response, USER_SESSION_COOKIE_NAME)


def clear_admin_session_cookie(response: Response) -> None:
    _clear_cookie(response, ADMIN_SESSION_COOKIE_NAME)


async def get_user_from_user_session(db: AsyncSession, session_token: str | None) -> User | None:
    raw = (session_token or "").strip()
    if not raw:
        return None

    stmt = select(User).where(
        User.session_token_hash == hash_session_token(raw),
        User.role == "user",
        User.auth_provider == "github",
        User.is_disabled.is_(False),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_from_admin_session(db: AsyncSession, session_token: str | None) -> User | None:
    raw = (session_token or "").strip()
    if not raw:
        return None

    stmt = select(User).where(
        User.session_token_hash == hash_session_token(raw),
        User.role == "admin",
        User.auth_provider == "local",
        User.is_disabled.is_(False),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
