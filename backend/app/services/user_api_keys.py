import hashlib
import logging

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserApiKey
from app.services.crypto import decrypt_secret, encrypt_secret
from app.config import settings

logger = logging.getLogger("prguard")

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
    stmt = (
        select(UserApiKey)
        .where(UserApiKey.user_id == user_id)
        .order_by(UserApiKey.created_at.desc(), UserApiKey.id.desc())
    )
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
        # Merge to ensure changes are tracked in async context
        await db.merge(row)
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
    print(f"SAVING TO user_api_keys - Provider: {normalized}, Key: {key_value[:10]}")

    encrypted = encrypt_secret(key_value)
    fingerprint = key_fingerprint(key_value)

    # REAL UPSERT using ON CONFLICT
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    
    stmt = pg_insert(UserApiKey).values(
        user_id=user_id,
        provider=normalized,
        encrypted_api_key=encrypted,
        key_fingerprint=fingerprint,
        is_active=make_active,
        updated_at=func.now()
    ).on_conflict_do_update(
        constraint="uq_user_provider_api_key",
        set_={
            "encrypted_api_key": encrypted,
            "key_fingerprint": fingerprint,
            "is_active": make_active,
            "updated_at": func.now()
        }
    )
    
    await db.execute(stmt)

    if make_active:
        other_stmt = select(UserApiKey).where(
            UserApiKey.user_id == user_id,
            UserApiKey.provider != normalized,
        )
        other_rows = (await db.execute(other_stmt)).scalars().all()
        for item in other_rows:
            item.is_active = False
            await db.merge(item)

    await db.commit()

    return {
        "provider": normalized,
        "masked_key": mask_key(key_value),
        "is_active": make_active,
        "fingerprint": fingerprint,
    }


async def delete_user_api_key(db: AsyncSession, *, user_id: str, provider: str) -> bool:
    normalized = validate_provider_or_400(provider)
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
    await db.flush()

    if was_active:
        remaining = await get_user_key_rows(db, user_id)
        if remaining:
            remaining[0].is_active = True

    await db.commit()
    return True


async def list_user_key_statuses(db: AsyncSession, *, user_id: str) -> dict:
    rows = await get_user_key_rows(db, user_id)
    items = []
    active_provider = None
    for row in rows:
        decrypted = decrypt_secret(row.encrypted_api_key)
        if row.is_active:
            active_provider = row.provider
        items.append(
            {
                "provider": row.provider,
                "has_key": bool(decrypted),
                "masked_key": mask_key(decrypted),
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
    print(f"FETCHING KEY for user: {user_id}, provider: {requested_provider}")
    normalized_requested = normalize_provider(requested_provider)
    if normalized_requested and normalized_requested not in ALLOWED_PROVIDERS:
        raise HTTPException(status_code=400, detail="Invalid provider. Use: claude, gpt, or gemini.")
    
    rows = await get_user_key_rows(db, user_id)
    if not rows:
        if settings.ENVIRONMENT == "development":
            # In development, try falling back to global environment keys.
            global_provider = normalized_requested or settings.MODEL_PROVIDER
            
            # Use consistent mapping for global keys
            key_map = {
                "claude": "ANTHROPIC_API_KEY",
                "gpt": "OPENAI_API_KEY",
                "gemini": "GEMINI_API_KEY"
            }
            attr_name = key_map.get(global_provider)
            global_key = getattr(settings, attr_name, None) if attr_name else None
            
            if global_key:
                return global_provider, global_key.strip()
            
            # If no global key either, just return empty so llm.generate can handle it gracefully.
            return global_provider or "claude", ""
            
        raise HTTPException(status_code=400, detail="No API key configured. Add one in Settings.")

    by_provider = {row.provider: row for row in reversed(rows)}

    if normalized_requested:
        selected = by_provider.get(normalized_requested)
        if selected:
            key = decrypt_secret(selected.encrypted_api_key)
            print(f"FETCHED KEY: {key[:10]}")
            return selected.provider, key
        
        # If requested not found, try fallback to any active/first key
        active = next((row for row in rows if row.is_active), None)
        selected = active or rows[0]
        logger.info(f"Requested provider '{normalized_requested}' not found. Falling back to '{selected.provider}'.")
        key = decrypt_secret(selected.encrypted_api_key)
        print('FETCHED KEY:', key[:10])
        return selected.provider, key

    active = next((row for row in rows if row.is_active), None)
    selected = active or rows[0]
    key = decrypt_secret(selected.encrypted_api_key)
    print(f"FETCHED KEY: {key[:10]}")
    return selected.provider, key


async def resolve_user_provider_keys(
    db: AsyncSession,
    *,
    user_id: str,
    requested_provider: str | None,
) -> list[tuple[str, str]]:
    """Return provider/key candidates in priority order for chat fallback."""
    print(f"FETCHING CANDIDATES for user: {user_id}, requested: {requested_provider}")
    
    normalized_requested = normalize_provider(requested_provider)
    rows = await get_user_key_rows(db, user_id)
    
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add_row(row: UserApiKey) -> None:
        p = (row.provider or "").strip().lower()
        if not p or p in seen:
            return
        key = decrypt_secret(row.encrypted_api_key)
        if key:
            print(f"FETCHED CANDIDATE: {p} {key[:10]}")
            candidates.append((p, key))
            seen.add(p)

    if rows:
        # Separate into active and inactive
        active_keys = [r for r in rows if r.is_active]
        inactive_keys = [r for r in rows if not r.is_active]
        
        # 1. Requested provider if active
        if normalized_requested:
            for r in active_keys:
                if r.provider == normalized_requested:
                    add_row(r)
                    break
        
        # 2. Other active keys
        for r in active_keys:
            add_row(r)
            
        # 3. Requested provider if inactive
        if normalized_requested:
            for r in inactive_keys:
                if r.provider == normalized_requested:
                    add_row(r)
                    break
                    
        # 4. Other inactive keys
        for r in inactive_keys:
            add_row(r)

    # 5. Fallback to global keys in development ONLY if no candidates found
    if not candidates and settings.ENVIRONMENT == "development":
        provider_order = [normalized_requested or settings.MODEL_PROVIDER, "claude", "gpt", "gemini"]
        key_map = {
            "claude": "ANTHROPIC_API_KEY",
            "gpt": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }

        for provider in provider_order:
            normalized = normalize_provider(provider)
            if normalized not in ALLOWED_PROVIDERS or normalized in seen:
                continue
            attr_name = key_map.get(normalized)
            global_key = getattr(settings, attr_name, None) if attr_name else None
            if global_key and global_key.strip():
                candidates.append((normalized, global_key.strip()))
                seen.add(normalized)

    return candidates
