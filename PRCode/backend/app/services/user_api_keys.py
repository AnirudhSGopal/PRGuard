import hashlib
from fastapi import HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserApiKey
from app.services.crypto import decrypt_secret, encrypt_secret

ALLOWED_PROVIDERS = {"claude", "gpt", "gemini"}

def normalize_provider(provider: str | None) -> str:
    normalized = (provider or "").strip().lower()
    if normalized == "gpt4o":
        normalized = "gpt"
    return normalized

def validate_provider_or_400(provider: str | None) -> str:
    normalized = normalize_provider(provider)
    if normalized not in ALLOWED_PROVIDERS:
        raise HTTPException(status_code=400, detail="Invalid provider. Use: claude, gpt, or gemini.")
    return normalized

def _validate_key_format(provider: str, api_key: str) -> None:
    key = (api_key or "").strip()
    if len(key) < 10:
        raise HTTPException(status_code=400, detail=f"Invalid {provider} API key.")

    if provider == "claude" and not key.startswith("sk-ant-"):
        raise HTTPException(status_code=400, detail="Claude API key must start with sk-ant-.")
    if provider == "gpt" and not key.startswith("sk-"):
        raise HTTPException(status_code=400, detail="OpenAI API key must start with sk-.")
    if provider == "gemini" and not key.startswith("AIza"):
        raise HTTPException(status_code=400, detail="Gemini API key must start with AIza.")

def mask_key(api_key: str) -> str:
    value = (api_key or "").strip()
    if not value:
        return "missing"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"

def key_fingerprint(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]

async def get_user_key_rows(db: AsyncSession, user_id: str) -> list[UserApiKey]:
    stmt = select(UserApiKey).where(UserApiKey.user_id == user_id).order_by(UserApiKey.created_at.desc(), UserApiKey.id.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())

async def set_active_provider(db: AsyncSession, user_id: str, provider: str) -> None:
    normalized = validate_provider_or_400(provider)
    rows = await get_user_key_rows(db, user_id)
    has_requested = False
    for row in rows:
        if row.provider == normalized:
            has_requested = True
            row.is_active = True
        else:
            row.is_active = False
    if not has_requested:
        raise HTTPException(status_code=404, detail=f"No API key configured for provider '{normalized}'.")
    await db.commit()

async def upsert_user_api_key(
    db: AsyncSession,
    *,
    user_id: str,
    provider: str,
    api_key: str,
    make_active: bool = True,
) -> dict:
    normalized = validate_provider_or_400(provider)
    key_value = (api_key or "").strip()
    _validate_key_format(normalized, key_value)

    encrypted = encrypt_secret(key_value)
    fingerprint = key_fingerprint(key_value)

    async with db.begin():
        if make_active:
            # Deactivate all other keys for this user
            other_keys_stmt = select(UserApiKey).where(
                UserApiKey.user_id == user_id, 
                UserApiKey.provider != normalized
            )
            other_keys_result = await db.execute(other_keys_stmt)
            for item in other_keys_result.scalars().all():
                item.is_active = False

        # Find existing key
        stmt = select(UserApiKey).where(
            UserApiKey.user_id == user_id,
            UserApiKey.provider == normalized,
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()

        if row:
            # Update existing row
            row.encrypted_api_key = encrypted
            row.key_fingerprint = fingerprint
            row.is_active = make_active
        else:
            # Create new row
            row = UserApiKey(
                user_id=user_id,
                provider=normalized,
                encrypted_api_key=encrypted,
                key_fingerprint=fingerprint,
                is_active=make_active,
            )
            db.add(row)
        
        # The `async with db.begin()` block handles the commit.

    return {
        "provider": normalized,
        "masked_key": mask_key(key_value),
        "is_active": bool(row.is_active),
        "fingerprint": fingerprint,
    }

async def delete_user_api_key(db: AsyncSession, *, user_id: str, provider: str) -> bool:
    normalized = validate_provider_or_400(provider)
    async with db.begin():
        stmt = select(UserApiKey).where(
            UserApiKey.user_id == user_id,
            UserApiKey.provider == normalized,
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return False

        was_active = bool(row.is_active)
        await db.delete(row)

        if was_active:
            remaining = await get_user_key_rows(db, user_id)
            if remaining:
                remaining[0].is_active = True
    return True

async def list_user_key_statuses(db: AsyncSession, *, user_id: str) -> dict:
    rows = await get_user_key_rows(db, user_id)
    items = []
    active_provider = None
    for row in rows:
        try:
            decrypted = decrypt_secret(row.encrypted_api_key)
            has_key = bool(decrypted)
            masked = mask_key(decrypted)
        except Exception as e:
            from app.services.user_api_keys import mask_key
            decrypted = ""
            has_key = False
            masked = "corrupt/invalid"

        if row.is_active:
            active_provider = row.provider
        items.append(
            {
                "provider": row.provider,
                "has_key": has_key,
                "masked_key": masked,
                "is_active": bool(row.is_active),
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
        )

    return {
        "items": sorted(items, key=lambda item: item["provider"]),
        "active_provider": active_provider,
        "has_any_key": any(item["has_key"] for item in items),
    }

async def resolve_user_provider_key(
    db: AsyncSession,
    *,
    user_id: str,
    requested_provider: str | None,
) -> tuple[str, str]:
    normalized_requested = normalize_provider(requested_provider)
    if normalized_requested and normalized_requested not in ALLOWED_PROVIDERS:
        raise HTTPException(status_code=400, detail="Invalid provider. Use: claude, gpt, or gemini.")
    rows = await get_user_key_rows(db, user_id)
    if not rows:
        raise HTTPException(status_code=400, detail="No API key configured. Add one in settings.")

    by_provider = {row.provider: row for row in rows}

    if normalized_requested:
        selected = by_provider.get(normalized_requested)
        if not selected:
            raise HTTPException(
                status_code=400,
                detail=f"No API key configured for provider '{normalized_requested}'.",
            )
        return selected.provider, decrypt_secret(selected.encrypted_api_key)

    active = next((row for row in rows if row.is_active), None)
    selected = active or rows[0]
    return selected.provider, decrypt_secret(selected.encrypted_api_key)
