from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware import requireUser
from app.models import User, get_db
from app.services.admin_state import record_api_key_status, record_user_activity
from app.services.user_api_keys import list_user_key_statuses, upsert_user_api_key, validate_provider_or_400

router = APIRouter()


class SaveUserApiKeyRequest(BaseModel):
    provider: str
    api_key: str
    make_active: bool = True


@router.post("/api-key")
async def save_authenticated_user_api_key(
    payload: SaveUserApiKeyRequest,
    current_user: User = Depends(requireUser),
    db: AsyncSession = Depends(get_db),
):
    normalized_provider = validate_provider_or_400(payload.provider)
    result = await upsert_user_api_key(
        db,
        user_id=current_user.id,
        provider=normalized_provider,
        api_key=payload.api_key,
        make_active=payload.make_active,
    )
    record_user_activity(user_id=current_user.id, username=current_user.username)
    record_api_key_status(
        user_id=current_user.id,
        username=current_user.username,
        provider=normalized_provider,
        api_key_present=bool(payload.api_key),
        validation_result="saved",
    )
    return result


@router.get("/profile")
async def get_authenticated_user_profile(
    current_user: User = Depends(requireUser),
    db: AsyncSession = Depends(get_db),
):
    key_status = await list_user_key_statuses(db, user_id=current_user.id)
    record_user_activity(user_id=current_user.id, username=current_user.username)
    return {
        "user_id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": (current_user.role or "").strip().lower() or "user",
        "auth_provider": (current_user.auth_provider or "").strip().lower()
        or ("local" if (current_user.role or "").strip().lower() == "admin" else "github"),
        "api_key_status": key_status,
    }
