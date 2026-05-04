from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User, get_db
from app.security import (
    create_github_oauth_url,
    decode_oauth_state,
    exchange_code_for_token,
    get_github_user,
    hash_access_token,
)
from app.services.admin_state import record_user_activity
from app.services.auth_session import (
    USER_SESSION_COOKIE_NAME,
    clear_user_session_cookie,
    get_user_from_user_session,
    issue_user_session,
)

router = APIRouter()
logger = logging.getLogger("prguard")


def _normalize_role(value: str | None) -> str:
    return "admin" if (value or "").strip().lower() == "admin" else "user"


def _normalize_provider(value: str | None) -> str:
    provider = (value or "").strip().lower()
    return provider if provider in {"local", "github"} else "github"


def _normalize_frontend_origin(value: str) -> str:
    parsed = urlparse((value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _build_redirect_page(target_url: str, status_text: str, oauth_payload: str | None = None) -> HTMLResponse:
    oauth_line = f"window.__PRGUARD_OAUTH__ = {oauth_payload};" if oauth_payload else ""
    return HTMLResponse(
        status_code=200,
        content=f"""<!DOCTYPE html>
<html>
    <head>
        <meta charset=\"utf-8\" />
        <meta http-equiv=\"refresh\" content=\"0;url={target_url}\" />
        <title>Redirecting...</title>
    </head>
    <body style=\"font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#0d0f12\">
        <p style=\"color:#aaa;font-size:14px\">{status_text}</p>
        <script>
            {oauth_line}
            window.location.replace({json.dumps(target_url)});
        </script>
    </body>
</html>""",
    )


def _build_session_payload(user: User) -> dict:
    role = _normalize_role(user.role)
    return {
        "user_id": user.id,
        "userId": user.id,
        "email": user.email,
        "role": role,
        "token": "cookie",
    }


@router.post("/login")
async def rejected_user_password_login() -> None:
    logger.warning("user_password_login_attempt rejected: oauth_required")
    raise HTTPException(status_code=403, detail="Users must sign in with GitHub OAuth. Admins must use /admin/login.")


@router.get("/github")
async def github_login(
    request: Request,
    frontend_origin: str = "",
    user_token: str | None = Cookie(default=None, alias=USER_SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
):
    origin = (frontend_origin or "").strip()
    if not origin:
        origin = (request.headers.get("origin") or "").strip()
    if not origin:
        referer = (request.headers.get("referer") or "").strip()
        if referer:
            parsed = urlparse(referer)
            origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""

    if not origin:
        origin = _normalize_frontend_origin((settings.FRONTEND_URL or "").strip())

    session_user = await get_user_from_user_session(db, user_token)
    if session_user and _normalize_role(session_user.role) == "admin":
        logger.info("signup_blocked_for_admin user_id=%s", session_user.id)
        return RedirectResponse(url=f"{origin}/admin/login?reason=admin_local_login_required")

    return RedirectResponse(url=create_github_oauth_url(frontend_origin=origin))


async def _load_or_create_github_user(
    db: AsyncSession,
    *,
    user_info: dict,
    access_token: str,
) -> User:
    github_id = str(user_info.get("id") or "").strip()
    github_login = (user_info.get("login") or "").strip()
    github_email = (user_info.get("email") or "").strip() or None
    if not github_id:
        raise HTTPException(status_code=401, detail="Invalid GitHub profile")

    token_hash = hash_access_token(access_token)

    stmt = select(User).where(User.github_id == github_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        if _normalize_role(user.role) == "admin" or _normalize_provider(user.auth_provider) == "local":
            logger.warning("oauth_callback denied: github_id=%s reason=admin_account", github_id)
            raise HTTPException(status_code=403, detail="Admin accounts cannot sign in with GitHub")
        user.role = "user"
        user.auth_provider = "github"
        user.github_id = user.github_id or github_id
        user.username = user.username or github_login or user.username
        user.email = user.email or github_email
        user.avatar_url = user_info.get("avatar_url")
        user.access_token = token_hash
        user.last_login_at = datetime.now(timezone.utc)
        logger.info("oauth_linked_existing user_id=%s source=github_id", user.id)
        return user

    if github_email:
        stmt = select(User).where(func.lower(User.email) == github_email.lower()).order_by(User.created_at.desc()).limit(1)
        result = await db.execute(stmt)
        user = result.scalars().first()
        if user:
            if _normalize_role(user.role) == "admin" or _normalize_provider(user.auth_provider) == "local":
                logger.warning("oauth_callback denied: email=%s reason=admin_account", github_email)
                raise HTTPException(status_code=403, detail="Admin accounts cannot sign in with GitHub")
            user.role = "user"
            user.auth_provider = "github"
            user.github_id = github_id
            user.username = user.username or github_login or user.username
            user.email = user.email or github_email
            user.avatar_url = user_info.get("avatar_url")
            user.access_token = token_hash
            user.last_login_at = datetime.now(timezone.utc)
            logger.info("oauth_linked_existing user_id=%s source=verified_email", user.id)
            return user

    if github_login:
        stmt = (
            select(User)
            .where(
                func.lower(User.username) == github_login.lower(),
                User.role == "user",
                User.auth_provider == "github",
            )
            .order_by(User.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        user = result.scalars().first()
        if user:
            user.role = "user"
            user.auth_provider = "github"
            user.github_id = github_id
            user.username = github_login
            user.email = github_email or user.email
            user.avatar_url = user_info.get("avatar_url")
            user.password_hash = None
            user.access_token = token_hash
            user.last_login_at = datetime.now(timezone.utc)
            logger.info("oauth_role_assignment user_id=%s role=user provider=github source=username_match", user.id)
            return user

    user = User(
        github_id=github_id,
        username=github_login or github_email or f"github-{github_id}",
        email=github_email,
        avatar_url=user_info.get("avatar_url"),
        access_token=token_hash,
        role="user",
        auth_provider="github",
        password_hash=None,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    logger.info("oauth_role_assignment user_id=%s role=user provider=github source=new_user", user.id)
    return user


@router.get("/github/callback")
async def github_callback(
    code: str = "",
    installation_id: str = "",
    error: str = "",
    state: str = "",
    user_token: str | None = Cookie(default=None, alias=USER_SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
):
    logger.info("oauth_callback_received error=%s has_code=%s installation_id=%s", bool(error), bool(code), bool(installation_id))
    if error:
        logger.warning("oauth_callback_failed reason=provider_error error=%s", error)
        raise HTTPException(status_code=400, detail=f"GitHub OAuth error: {error}")
    if not code:
        logger.warning("oauth_callback_failed reason=missing_code")
        raise HTTPException(status_code=400, detail="Missing OAuth code")

    access_token = await exchange_code_for_token(code)
    if not access_token:
        logger.warning("oauth_callback_failed reason=token_exchange_failed")
        raise HTTPException(status_code=401, detail="Failed to obtain access token from GitHub")

    user_info = await get_github_user(access_token)
    if "id" not in user_info or "login" not in user_info:
        logger.warning("oauth_callback_failed reason=invalid_github_profile")
        raise HTTPException(status_code=401, detail="Invalid GitHub token")

    state_data = decode_oauth_state(state)
    state_frontend = _normalize_frontend_origin(str(state_data.get("frontend_origin", "")))
    configured_frontend = _normalize_frontend_origin((settings.FRONTEND_URL or "").strip())
    frontend_url = state_frontend or configured_frontend
    if not frontend_url:
        raise HTTPException(status_code=500, detail="FRONTEND_URL is not configured and no valid frontend_origin was provided")

    prior_session_user = await get_user_from_user_session(db, user_token)

    try:
        db_user = await _load_or_create_github_user(db, user_info=user_info, access_token=access_token)
    except HTTPException as exc:
        if exc.status_code == 403 and str(exc.detail) == "Admin accounts cannot sign in with GitHub":
            admin_login_target = f"{frontend_url}/admin/login?reason=admin_local_login_required"
            response = _build_redirect_page(admin_login_target, "Admin account detected. Redirecting to admin login...")
            is_prod = settings.ENVIRONMENT == "production"
            clear_user_session_cookie(response)
            response.delete_cookie(
                key="gh_token",
                path="/",
                httponly=True,
                samesite="none" if is_prod else "lax",
                secure=is_prod,
            )
            return response
        raise

    db_role = _normalize_role(db_user.role)
    if db_role != "user":
        logger.error("oauth_callback_blocked user_id=%s role=%s", db_user.id, db_role)
        admin_login_target = f"{frontend_url}/admin/login?reason=admin_local_login_required"
        response = _build_redirect_page(admin_login_target, "Admin accounts must use email login.")
        clear_user_session_cookie(response)
        return response

    payload = json.dumps(_build_session_payload(db_user))
    callback_target = f"{frontend_url}/auth/callback"
    response = _build_redirect_page(callback_target, "Signing in, please wait...", payload)

    is_prod = settings.ENVIRONMENT == "production"
    response.set_cookie(
        key="gh_token",
        value=access_token,
        httponly=True,
        secure=is_prod,
        samesite="none" if is_prod else "lax",
        max_age=60 * 60 * 24,
        path="/",
    )
    response.delete_cookie(
        key="admin_session",
        path="/",
        httponly=True,
        samesite="none" if is_prod else "lax",
        secure=is_prod,
    )

    if prior_session_user and prior_session_user.id != db_user.id:
        logger.info("session_rotated previous_user_id=%s new_user_id=%s", prior_session_user.id, db_user.id)
        prior_session_user.session_token_hash = None

    issue_user_session(db_user, response)
    await db.commit()
    logger.info("oauth_callback_succeeded user_id=%s role=user", db_user.id)
    return response


@router.get("/me")
async def get_current_user(
    user_token: str | None = Cookie(default=None, alias=USER_SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
):
    db_user = await get_user_from_user_session(db, user_token)
    if not db_user:
        return {
            "authenticated": False,
            "user_id": None,
            "id": None,
            "login": None,
            "name": None,
            "avatar_url": None,
            "email": None,
            "html_url": "",
            "is_admin": False,
            "role": None,
            "auth_provider": None,
        }

    record_user_activity(
        user_id=str(db_user.id),
        username=db_user.username,
    )

    return {
        "authenticated": True,
        "user_id": db_user.id,
        "id": db_user.id,
        "login": db_user.username,
        "name": db_user.username,
        "avatar_url": db_user.avatar_url,
        "email": db_user.email,
        "html_url": "",
        "is_admin": _normalize_role(db_user.role) == "admin",
        "role": _normalize_role(db_user.role),
        "auth_provider": _normalize_provider(db_user.auth_provider),
    }


@router.post("/logout")
async def logout(
    response: Response,
    user_token: str | None = Cookie(default=None, alias=USER_SESSION_COOKIE_NAME),
    gh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    session_user = await get_user_from_user_session(db, user_token)
    session_role = _normalize_role(session_user.role) if session_user else "user"
    if session_user:
        logger.info("logout_requested user_id=%s role=%s", session_user.id, session_role)
        session_user.session_token_hash = None

    if gh_token:
        token_hash = hash_access_token(gh_token)
        stmt = select(User).where(User.access_token == token_hash)
        result = await db.execute(stmt)
        matching_users = result.scalars().all()
        for db_user in matching_users:
            db_user.access_token = ""

    await db.commit()

    clear_user_session_cookie(response)
    is_prod = settings.ENVIRONMENT == "production"
    response.delete_cookie(
        key="gh_token",
        path="/",
        httponly=True,
        samesite="none" if is_prod else "lax",
        secure=is_prod,
    )
    redirect_target = "/login"
    return {"status": "logged out", "redirect": redirect_target, "role": session_role}


@router.get("/callback")
async def github_app_callback(
    code: str = "",
    installation_id: str = "",
):
    return {
        "status": "ok",
        "installation_id": installation_id,
        "message": "GitHub App installed successfully",
    }
