import logging

from fastapi import APIRouter, HTTPException, Response, Cookie, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from app.config import settings
from app.models import get_db, User
from app.security import hash_access_token
from app.services.crypto import encrypt_secret
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.security import (
    create_github_oauth_url,
    exchange_code_for_token,
    get_github_user,
)
from app.services.admin_state import record_user_activity
from app.services.auth_session import issue_user_session, clear_user_session_cookie, USER_SESSION_COOKIE_NAME
from app.middleware import get_current_user as get_session_user, get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter()


# ── GitHub OAuth ──────────────────────────────────────────────────────────────

@router.get("/github")
async def github_login(frontend_origin: str = ""):
    return RedirectResponse(url=create_github_oauth_url(frontend_origin))


@router.get("/github/callback")
@router.post("/github/callback")
async def github_callback(
    code: str = "",
    installation_id: str = "",
    error: str = "",
    state: str = "",
    db: AsyncSession = Depends(get_db),
):
    if error:
        raise HTTPException(status_code=400, detail=f"GitHub OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth code")

    access_token = await exchange_code_for_token(code)
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Failed to obtain access token from GitHub. "
                   "The code may have expired — please try again.",
        )

    try:
        user_info = await get_github_user(access_token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch GitHub user: {str(e)}")

    if "login" not in user_info:
        raise HTTPException(status_code=401, detail="Invalid GitHub token")

    oauth_login = user_info.get("login") or ""
    oauth_email = user_info.get("email") or ""
    
    # Check if this user should be an admin
    is_admin = settings.is_admin_identity(login=oauth_login, email=oauth_email)
    role = "admin" if is_admin else "user"
    redirect_target = "/admin/dashboard" if is_admin else "/dashboard"

    stmt = select(User).where(User.github_id == str(user_info["id"]))
    result = await db.execute(stmt)
    db_user = result.scalar_one_or_none()

    token_hash = hash_access_token(access_token)
    encrypted_raw_token = encrypt_secret(access_token)
    if db_user:
        db_user.access_token = token_hash
        db_user.raw_github_token = encrypted_raw_token
        db_user.username = oauth_login
        db_user.avatar_url = user_info.get("avatar_url")
        db_user.email = oauth_email
        db_user.role = role
        db_user.auth_provider = "github"
    else:
        db_user = User(
            github_id=str(user_info["id"]),
            username=oauth_login,
            email=oauth_email,
            avatar_url=user_info.get("avatar_url"),
            access_token=token_hash,
            raw_github_token=encrypted_raw_token,
            role=role,
            auth_provider="github",
        )
        db.add(db_user)

    await db.commit()
    await db.refresh(db_user)

    # ── Build response ──
    frontend_url = settings.FRONTEND_URL.strip()
    response = HTMLResponse(
        status_code=200,
        content=f"""<!DOCTYPE html>
<html>
    <head>
        <meta charset="utf-8" />
        <meta http-equiv="refresh" content="0;url={frontend_url}{redirect_target}" />
        <title>Signing in…</title>
    </head>
    <body style="font-family:sans-serif;display:flex;align-items:center;
                             justify-content:center;height:100vh;margin:0;background:#0d0f12">
        <p style="color:#aaa;font-size:14px">Signing in, please wait…</p>
        <script>
            window.location.replace("{frontend_url}{redirect_target}");
        </script>
    </body>
</html>""",
    )

    # ── Issue formal session ──
    issue_user_session(db_user, response)
    await db.commit()
    
    # ── Also keep gh_token for legacy compatibility in this transition ──
    is_prod = settings.ENVIRONMENT == "production"
    response.set_cookie(
        key      = "gh_token",
        value    = access_token,
        httponly = True,
        secure   = is_prod,
        samesite = "none" if is_prod else "lax",
        max_age  = 60 * 60 * 24, 
        path     = "/",
    )
    
    return response


@router.get("/me")
async def get_current_user_profile(
    user: User | None = Depends(get_optional_user),
):
    """
    Optimized profile check using local session instead of calling GitHub API every time.
    """
    if not user:
        return {"authenticated": False}

    return {
        "login":      user.username,
        "name":       user.username,
        "avatar_url": user.avatar_url,
        "email":      user.email,
        "html_url":   f"https://github.com/{user.username}",
        "is_admin":   user.role == "admin",
    }


@router.post("/logout")
async def logout(
    response: Response,
    user: User = Depends(get_session_user),
    db: AsyncSession = Depends(get_db),
):
    if user:
        user.session_token_hash = None
        await db.commit()

    clear_user_session_cookie(response)
    response.delete_cookie(key="gh_token", path="/")
    return {"status": "logged out"}


# ── GitHub App install callback ───────────────────────────────────────────────

@router.get("/callback")
async def github_app_callback(
    code: str = "",
    installation_id: str = "",
):
    return {
        "status":          "ok",
        "installation_id": installation_id,
        "message":         "GitHub App installed successfully",
    }