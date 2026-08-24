from __future__ import annotations

from datetime import datetime, timezone
import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.services.admin_auth import hash_password

logger = logging.getLogger("prguard")


async def _find_user_by_username(db: AsyncSession, username: str) -> User | None:
    stmt = select(User).where(func.lower(User.username) == username.lower()).order_by(User.created_at.desc()).limit(1)
    result = await db.execute(stmt)
    return result.scalars().first()


async def _find_user_by_email(db: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(func.lower(User.email) == email.lower()).order_by(User.created_at.desc()).limit(1)
    result = await db.execute(stmt)
    return result.scalars().first()


async def _next_available_username(db: AsyncSession, preferred: str) -> str:
    base = (preferred or "admin").strip() or "admin"
    candidate = base
    suffix = 1
    while await _find_user_by_username(db, candidate):
        suffix += 1
        candidate = f"{base}_{suffix}"
    return candidate


async def ensure_default_admin(db: AsyncSession) -> None:
    username = (settings.ADMIN_USERNAME or "").strip()
    email = (settings.ADMIN_EMAIL or "").strip() or None
    password = (settings.ADMIN_PASSWORD or "").strip()

    if not username or not password:
        return

    user = None

    if email:
        by_email = await _find_user_by_email(db, email)
        if by_email and by_email.role == "admin" and by_email.auth_provider == "local":
            user = by_email

    if not user:
        by_username = await _find_user_by_username(db, username)
        if by_username and by_username.role == "admin" and by_username.auth_provider == "local":
            user = by_username

    email_to_apply = email
    if email_to_apply:
        existing_with_email = await _find_user_by_email(db, email_to_apply)
        if existing_with_email and (not user or existing_with_email.id != user.id):
            logger.warning(
                "admin_bootstrap email in use by non-admin/local account; creating admin without email email=%s user_id=%s",
                email_to_apply,
                existing_with_email.id,
            )
            email_to_apply = None

    now = datetime.now(timezone.utc)
    if user:
        user.role = "admin"
        user.auth_provider = "local"
        user.email = email_to_apply or user.email
        user.is_disabled = False
        user.password_hash = hash_password(password)
        user.github_id = None
        if user.access_token is None:
            user.access_token = ""
        if user.created_at is None:
            user.created_at = now
    else:
        # Never hijack a non-admin user account by username collision.
        create_username = username
        existing_with_username = await _find_user_by_username(db, create_username)
        if existing_with_username:
            logger.warning(
                "admin_bootstrap username collision with existing non-admin/local account username=%s user_id=%s",
                create_username,
                existing_with_username.id,
            )
            create_username = await _next_available_username(db, f"{create_username}_admin")

        user = User(
            github_id=None,
            username=create_username,
            email=email_to_apply,
            password_hash=hash_password(password),
            role="admin",
            auth_provider="local",
            access_token="",
            is_disabled=False,
            created_at=now,
        )
        db.add(user)
        logger.info("admin_bootstrap created new admin user_id=%s username=%s", user.id, create_username)

    try:
        await db.commit()
    except IntegrityError:
        # Another startup worker may create/update the admin row concurrently.
        await db.rollback()

        recovered = None
        if email_to_apply:
            by_email = await _find_user_by_email(db, email_to_apply)
            if by_email and by_email.role == "admin" and by_email.auth_provider == "local":
                recovered = by_email

        if not recovered:
            by_username = await _find_user_by_username(db, username)
            if by_username and by_username.role == "admin" and by_username.auth_provider == "local":
                recovered = by_username

        if not recovered:
            raise

        recovered.password_hash = hash_password(password)
        recovered.is_disabled = False
        recovered.role = "admin"
        recovered.auth_provider = "local"
        if email_to_apply:
            recovered.email = email_to_apply
        recovered.github_id = None
        if recovered.access_token is None:
            recovered.access_token = ""
        if recovered.created_at is None:
            recovered.created_at = now

        await db.commit()
