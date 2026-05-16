from datetime import datetime, timedelta, timezone
import logging

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.middleware import admin_required
from app.models import User, get_db
from app.models.api_key import UserApiKey
from app.services.auth_session import (
    ADMIN_SESSION_COOKIE_NAME,
    authenticate_admin_credentials,
    clear_admin_session_cookie,
    get_user_from_admin_session,
    issue_admin_session,
)
from app.services.admin_state import get_recent_chat_logs
from app.services.crypto import decrypt_secret
from app.services.user_api_keys import mask_key

router = APIRouter()
logger = logging.getLogger("prguard")


class AdminLoginPayload(BaseModel):
    email: str
    password: str


class AdminUserPatchPayload(BaseModel):
    role: str | None = None
    is_disabled: bool | None = None
    reset_api_key_status: bool = False


def _looks_like_valid_key(provider: str, key_value: str) -> bool:
    value = (key_value or "").strip()
    if not value:
        return False
    if provider == "claude":
        return value.startswith("sk-ant-")
    if provider == "gpt":
        return value.startswith("sk-")
    if provider == "gemini":
        return value.startswith("AIza")
    return len(value) >= 10


def _derive_user_key_status(user: User, key_rows: list[UserApiKey]) -> tuple[str, str, str]:
    if key_rows:
        for row in key_rows:
            try:
                decrypted = decrypt_secret(row.encrypted_api_key)
            except Exception:
                return "invalid", "corrupt", "missing"

            if not _looks_like_valid_key(row.provider, decrypted):
                return "invalid", "format_invalid", mask_key(decrypted)

        active = next((item for item in key_rows if item.is_active), key_rows[0])
        decrypted = decrypt_secret(active.encrypted_api_key)
        return "added", "valid", mask_key(decrypted)

    if (user.api_key or "").strip():
        return "added", "legacy_stored", mask_key(user.api_key or "")

    return "missing", "missing", "missing"


def _usage_error_count_by_user() -> dict[str, int]:
    errors: dict[str, int] = {}
    for item in get_recent_chat_logs(limit=200):
        if item.get("status") != "failure":
            continue
        uid = str(item.get("user_id") or "")
        if not uid:
            continue
        errors[uid] = errors.get(uid, 0) + 1
    return errors


def _format_user_row(user: User, key_rows: list[UserApiKey], usage_errors: dict[str, int]) -> dict:
    key_status, key_validation, masked_key = _derive_user_key_status(user, key_rows)
    
    # Try to get the full unmasked key for display
    full_key = ""
    if key_rows:
        try:
            for row in key_rows:
                decrypted = decrypt_secret(row.encrypted_api_key)
                if decrypted and _looks_like_valid_key(row.provider, decrypted):
                    full_key = decrypted
                    break
        except Exception:
            full_key = ""
    
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "is_disabled": bool(user.is_disabled),
        "api_key_status": key_status,
        "api_key_validation": key_validation,
        "api_key_masked": masked_key,
        "api_key_full": full_key,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login_at.isoformat() if user.last_login_at else None,
        "api_key_usage_errors": usage_errors.get(user.id, 0),
    }


def _as_utc(dt: datetime | None) -> datetime | None:
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@router.post("/login")
async def admin_login(
    payload: AdminLoginPayload,
    response: Response,
    admin_token: str | None = Cookie(default=None, alias=ADMIN_SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_admin_credentials(db, email=payload.email, password=payload.password)

    prior_session_user = await get_user_from_admin_session(db, admin_token)
    if prior_session_user and prior_session_user.id != user.id:
        logger.info("session_rotated previous_user_id=%s new_user_id=%s", prior_session_user.id, user.id)
        prior_session_user.session_token_hash = None

    issue_admin_session(user, response)
    is_prod = settings.ENVIRONMENT == "production"
    response.delete_cookie(
        key="gh_token",
        path="/",
        httponly=True,
        samesite="none" if is_prod else "lax",
        secure=is_prod,
    )
    await db.commit()

    logger.info("admin_login_success user_id=%s", user.id)
    return {
        "user_id": user.id,
        "userId": user.id,
        "email": user.email,
        "role": "admin",
        "token": "cookie",
    }


@router.get("/me")
async def admin_me(
    admin_token: str | None = Cookie(default=None, alias=ADMIN_SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_from_admin_session(db, admin_token)
    if not user:
        return {
            "authenticated": False,
            "user_id": None,
            "id": None,
            "username": None,
            "email": None,
            "role": None,
        }

    return {
        "authenticated": True,
        "user_id": user.id,
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
    }


@router.post("/logout")
async def admin_logout(
    response: Response,
    admin_token: str | None = Cookie(default=None, alias=ADMIN_SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_from_admin_session(db, admin_token)
    admin_id = user.id if user else ""
    logger.info("admin_logout_requested admin_user_id=%s", admin_id or "unknown")
    if user:
        user.session_token_hash = None
        await db.commit()

    clear_admin_session_cookie(response)
    return {"status": "logged_out", "redirect": "/"}


@router.get("/users")
async def admin_users(
    _: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db),
    search: str = "",
    role: str = "all",
    key_status: str = "all",
):
    users_result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = list(users_result.scalars().all())

    key_result = await db.execute(select(UserApiKey))
    key_rows = list(key_result.scalars().all())
    keys_by_user: dict[str, list[UserApiKey]] = {}
    for row in key_rows:
        keys_by_user.setdefault(row.user_id, []).append(row)

    usage_errors = _usage_error_count_by_user()

    search_value = (search or "").strip().lower()
    role_value = (role or "all").strip().lower()
    key_filter = (key_status or "all").strip().lower()

    items = []
    for user in users:
        row = _format_user_row(user, keys_by_user.get(user.id, []), usage_errors)
        if search_value:
            haystack = f"{row['username']} {row['email'] or ''}".lower()
            if search_value not in haystack:
                continue
        if role_value in {"user", "admin"} and row["role"] != role_value:
            continue
        if key_filter in {"missing", "invalid", "added"} and row["api_key_status"] != key_filter:
            continue
        items.append(row)

    active_threshold = datetime.now(timezone.utc) - timedelta(days=30)
    active_users = sum(
        1
        for user in users
        if (_as_utc(user.last_login_at) or datetime.min.replace(tzinfo=timezone.utc)) >= active_threshold and not user.is_disabled
    )

    return {
        "summary": {
            "total_users": len(users),
            "active_users": active_users,
            "admins": sum(1 for user in users if user.role == "admin" and not user.is_disabled),
            "missing_api_keys": sum(1 for row in items if row["api_key_status"] == "missing"),
            "invalid_api_keys": sum(1 for row in items if row["api_key_status"] == "invalid"),
        },
        "users": items,
        "count": len(items),
    }


@router.get("/user/{user_id}")
async def admin_user_detail(
    user_id: str,
    _: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    key_stmt = select(UserApiKey).where(UserApiKey.user_id == user.id)
    key_result = await db.execute(key_stmt)
    key_rows = list(key_result.scalars().all())
    usage_errors = _usage_error_count_by_user()
    return _format_user_row(user, key_rows, usage_errors)


@router.patch("/user/{user_id}")
async def admin_update_user(
    user_id: str,
    payload: AdminUserPatchPayload,
    _: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.role is not None:
        role_value = payload.role.strip().lower()
        if role_value not in {"user", "admin"}:
            raise HTTPException(status_code=400, detail="role must be 'user' or 'admin'")
        if role_value == "admin" and (user.auth_provider or "").strip().lower() != "local":
            raise HTTPException(status_code=400, detail="Only local accounts can be assigned admin role")
        user.role = role_value

    if payload.is_disabled is not None:
        user.is_disabled = bool(payload.is_disabled)
        if user.is_disabled:
            user.session_token_hash = None

    if payload.reset_api_key_status:
        user.api_key = None
        await db.execute(delete(UserApiKey).where(UserApiKey.user_id == user.id))

    await db.commit()

    key_stmt = select(UserApiKey).where(UserApiKey.user_id == user.id)
    key_result = await db.execute(key_stmt)
    key_rows = list(key_result.scalars().all())
    usage_errors = _usage_error_count_by_user()
    return {
        "status": "updated",
        "user": _format_user_row(user, key_rows, usage_errors),
    }


@router.get("/api-keys-status")
async def admin_api_keys_status(
    _: User = Depends(admin_required),
    db: AsyncSession = Depends(get_db),
):
    users_result = await db.execute(select(User))
    users = list(users_result.scalars().all())

    key_result = await db.execute(select(UserApiKey))
    key_rows = list(key_result.scalars().all())
    keys_by_user: dict[str, list[UserApiKey]] = {}
    for row in key_rows:
        keys_by_user.setdefault(row.user_id, []).append(row)

    usage_errors = _usage_error_count_by_user()
    items = []
    for user in users:
        row = _format_user_row(user, keys_by_user.get(user.id, []), usage_errors)
        items.append(
            {
                "user_id": row["id"],
                "username": row["username"],
                "status": row["api_key_status"],
                "validation_result": row["api_key_validation"],
                "masked_key": row["api_key_masked"],
                "usage_errors": row["api_key_usage_errors"],
            }
        )

    return {"items": items}


@router.get("/logs")
async def admin_logs(_: User = Depends(admin_required)):
    logs = get_recent_chat_logs(limit=50)
    success_count = sum(1 for item in logs if item["status"] == "success")
    failure_count = sum(1 for item in logs if item["status"] == "failure")

    return {
        "requests": logs,
        "summary": {
            "total": len(logs),
            "success": success_count,
            "failure": failure_count,
        },
    }
