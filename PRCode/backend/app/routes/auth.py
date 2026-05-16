import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Cookie
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from app.config import settings
from app.models import User, get_db
from app.security import (
    create_github_oauth_url,
    decode_oauth_state,
    exchange_code_for_token,
    get_github_user,
    hash_access_token,
)
from app.services.auth_session import (
    USER_SESSION_COOKIE_NAME,
    clear_user_session_cookie,
    get_user_from_user_session,
    issue_user_session,
)
from app.limiter import auth_limiter

router = APIRouter()
logger = logging.getLogger("prguard")

@router.get("/github")
async def github_login(request: Request, frontend_origin: str = ""):
    # Rate limit OAuth attempts
    auth_limiter.check(request.client.host)
    
    url = create_github_oauth_url(frontend_origin=frontend_origin)
    return RedirectResponse(url)

@router.get("/github/callback")
async def github_callback(
    request: Request,
    response: Response,
    code: str,
    state: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    # Rate limit OAuth callbacks
    auth_limiter.check(request.client.host)
    
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    access_token = await exchange_code_for_token(code)
    if not access_token:
        raise HTTPException(status_code=401, detail="Failed to retrieve access token")

    gh_user = await get_github_user(access_token)
    github_id = str(gh_user.get("id"))
    email = gh_user.get("email")
    username = gh_user.get("login")

    # Link or create user
    from sqlalchemy import select
    stmt = select(User).where(User.github_id == github_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user and email:
        stmt = select(User).where(User.email == email)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

    if not user:
        from datetime import datetime, timezone
        user = User(
            github_id=github_id,
            username=username,
            email=email,
            avatar_url=gh_user.get("avatar_url"),
            access_token=access_token,
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
    else:
        user.access_token = access_token
        user.avatar_url = gh_user.get("avatar_url")
        user.username = username

    # Update session
    session_token = issue_user_session(user, response)
    
    # Secure cookie for the raw token (consistency check)
    is_prod = settings.ENVIRONMENT == "production"
    response.set_cookie(
        key="gh_token",
        value=hash_access_token(access_token),
        httponly=True,
        secure=is_prod,
        samesite="none" if is_prod else "lax",
        max_age=settings.ADMIN_SESSION_TTL_SECONDS, # Synced TTL
        path="/",
    )

    await db.commit()
    
    # Redirect back to frontend
    state_data = decode_oauth_state(state)
    target = state_data.get("frontend_origin") or settings.FRONTEND_URL
    return RedirectResponse(f"{target}/dashboard?login=success")

@router.get("/me")
async def get_me(
    user_token: str | None = Cookie(default=None, alias=USER_SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db)
):
    user = await get_user_from_user_session(db, user_token)
    if not user:
        return None
    return {
        "id": user.id,
        "login": user.username,
        "username": user.username,
        "email": user.email,
        "avatar_url": user.avatar_url,
        "role": user.role
    }

@router.post("/logout")
async def logout(response: Response):
    clear_user_session_cookie(response)
    is_prod = settings.ENVIRONMENT == "production"
    response.delete_cookie(
        key="gh_token",
        path="/",
        httponly=True,
        samesite="none" if is_prod else "lax",
        secure=is_prod,
    )
    return {"status": "ok"}
