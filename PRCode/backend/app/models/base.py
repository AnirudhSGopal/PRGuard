from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings
from app.services.db_migrations import apply_pending_migrations

logger = logging.getLogger("prguard")


def _build_engine():
    database_url = settings.database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL must be set before the backend starts.")

    engine_kwargs: dict[str, object] = {
        "echo": settings.is_development(),
        "pool_pre_ping": True,
    }

    if database_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        engine_kwargs["poolclass"] = NullPool
    else:
        db_url_lower = database_url.lower()
        is_neon = "neon.tech" in db_url_lower
        is_supabase_pooler = "pooler.supabase.com" in db_url_lower or ":6543/" in db_url_lower
        connect_args: dict[str, object] = {
            "timeout": max(int(settings.DB_CONNECT_TIMEOUT), 1),
            "command_timeout": max(int(settings.DB_CONNECT_TIMEOUT), 1),
        }

        print(f"DEBUG: database_url={database_url}")
        if is_neon or is_supabase_pooler:
            # PgBouncer-based poolers work best with asyncpg statement cache disabled.
            connect_args["statement_cache_size"] = 0
            # Some versions might use this key instead or in addition
            connect_args["prepared_statement_cache_size"] = 0
        
        print(f"DEBUG: connect_args={connect_args}")
        logger.info(f"Database engine connect_args: {connect_args}")
        engine_kwargs.update(
            {
                "pool_size": max(int(settings.DB_POOL_SIZE), 1),
                "max_overflow": max(int(settings.DB_MAX_OVERFLOW), 0),
                "pool_timeout": max(int(settings.DB_POOL_TIMEOUT), 1),
                "pool_recycle": max(int(settings.DB_POOL_RECYCLE), 0),
                "pool_use_lifo": True,
                "connect_args": connect_args,
            }
        )

    return create_async_engine(database_url, **engine_kwargs)


engine = _build_engine()

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def ping_database() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def verify_database_connection() -> None:
    delay = float(settings.DB_RETRY_DELAY_SECONDS)
    max_delay = float(settings.DB_MAX_RETRY_DELAY_SECONDS)
    attempts = max(int(settings.DB_CONNECT_RETRIES), 1)
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            await ping_database()
            logger.info("Database connection verified: %s", settings.database_host_summary())
            return
        except Exception as exc:  # pragma: no cover - exercised in deployment failures
            last_error = exc
            logger.warning(
                "Database connection attempt %s/%s failed: %s",
                attempt,
                attempts,
                exc,
            )
            if attempt < attempts:
                await asyncio.sleep(delay)
                delay = min(delay * 2.0, max_delay)

    raise RuntimeError(
        f"Unable to connect to the configured database after {attempts} attempts."
    ) from last_error


async def init_db():
    await verify_database_connection()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await apply_pending_migrations(conn)