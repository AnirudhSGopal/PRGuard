from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Awaitable, Callable

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection


MigrationFn = Callable[[AsyncConnection], Awaitable[None]]


@dataclass(frozen=True)
class Migration:
    name: str
    upgrade: MigrationFn


async def _ensure_migration_table(conn: AsyncConnection) -> None:
    await conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
            """
        )
    )


def sync_users_table_schema(sync_conn) -> None:
    inspector = inspect(sync_conn)
    try:
        column_info = {item["name"]: item for item in inspector.get_columns("users")}
    except Exception:
        return

    columns = set(column_info)
    dialect = sync_conn.dialect.name
    timestamp_type = "TIMESTAMPTZ" if dialect != "sqlite" else "TIMESTAMP"

    if dialect == "sqlite" and column_info.get("github_id") and not column_info["github_id"].get("nullable", True):
        sync_conn.execute(text("PRAGMA foreign_keys=OFF"))
        sync_conn.execute(
            text(
                """
                CREATE TABLE users_new (
                    id VARCHAR PRIMARY KEY,
                    github_id VARCHAR UNIQUE,
                    username VARCHAR NOT NULL,
                    email VARCHAR,
                    password_hash TEXT,
                    role VARCHAR(20) DEFAULT 'user' NOT NULL,
                    auth_provider VARCHAR(20) DEFAULT 'github' NOT NULL,
                    api_key TEXT,
                    avatar_url VARCHAR,
                    access_token VARCHAR NOT NULL,
                    session_token_hash VARCHAR(128),
                    is_disabled BOOLEAN DEFAULT FALSE NOT NULL,
                    last_login_at TIMESTAMP,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
        )
        sync_conn.execute(
            text(
                """
                INSERT INTO users_new (
                    id, github_id, username, email, password_hash, role, auth_provider,
                    api_key, avatar_url, access_token, session_token_hash, is_disabled,
                    last_login_at, created_at
                )
                SELECT
                    id,
                    CASE WHEN role = 'admin' THEN NULL ELSE github_id END,
                    username,
                    email,
                    CASE WHEN role = 'admin' THEN password_hash ELSE NULL END,
                    CASE WHEN role = 'admin' THEN 'admin' ELSE 'user' END,
                    CASE WHEN role = 'admin' THEN 'local' ELSE 'github' END,
                    api_key,
                    avatar_url,
                    COALESCE(access_token, ''),
                    session_token_hash,
                    COALESCE(is_disabled, 0),
                    last_login_at,
                    created_at
                FROM users
                """
            )
        )
        sync_conn.execute(text("DROP TABLE users"))
        sync_conn.execute(text("ALTER TABLE users_new RENAME TO users"))
        sync_conn.execute(text("PRAGMA foreign_keys=ON"))
        return

    additions: list[tuple[str, str]] = []

    if "password_hash" not in columns:
        additions.append(("password_hash", "TEXT"))
    if "role" not in columns:
        additions.append(("role", "VARCHAR(20) DEFAULT 'user'"))
    if "auth_provider" not in columns:
        additions.append(("auth_provider", "VARCHAR(20) DEFAULT 'github'"))
    if "github_id" not in columns:
        additions.append(("github_id", "TEXT"))
    if "api_key" not in columns:
        additions.append(("api_key", "TEXT"))
    if "access_token" not in columns:
        additions.append(("access_token", "TEXT"))
    if "session_token_hash" not in columns:
        additions.append(("session_token_hash", "VARCHAR(128)"))
    if "is_disabled" not in columns:
        additions.append(("is_disabled", "BOOLEAN DEFAULT FALSE"))
    if "last_login_at" not in columns:
        additions.append(("last_login_at", timestamp_type))

    for col_name, col_type in additions:
        sync_conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))

    if any(name == "role" for name, _ in additions):
        sync_conn.execute(text("UPDATE users SET role='user' WHERE role IS NULL OR role=''"))

    # Enforce strict role vocabulary in existing rows.
    sync_conn.execute(text("UPDATE users SET role = LOWER(COALESCE(role, 'user'))"))
    sync_conn.execute(text("UPDATE users SET role = 'user' WHERE role NOT IN ('admin', 'user')"))

    if any(name == "auth_provider" for name, _ in additions):
        sync_conn.execute(
            text("UPDATE users SET auth_provider = CASE WHEN role = 'admin' THEN 'local' ELSE 'github' END")
        )

    sync_conn.execute(
        text("UPDATE users SET auth_provider = CASE WHEN role = 'admin' THEN 'local' ELSE COALESCE(NULLIF(LOWER(auth_provider), ''), 'github') END")
    )
    sync_conn.execute(text("UPDATE users SET auth_provider = 'github' WHERE auth_provider NOT IN ('local', 'github')"))
    sync_conn.execute(text("UPDATE users SET github_id = NULL WHERE role = 'admin'"))
    sync_conn.execute(text("UPDATE users SET password_hash = NULL WHERE role != 'admin'"))

    if any(name == "is_disabled" for name, _ in additions):
        if dialect == "sqlite":
            sync_conn.execute(text("UPDATE users SET is_disabled=0 WHERE is_disabled IS NULL"))
        else:
            sync_conn.execute(text("UPDATE users SET is_disabled=FALSE WHERE is_disabled IS NULL"))


async def _upgrade_users_schema(conn: AsyncConnection) -> None:
    await conn.run_sync(sync_users_table_schema)


async def _upgrade_indexes(conn: AsyncConnection) -> None:
    statements = [
        "CREATE INDEX IF NOT EXISTS idx_users_access_token ON users(access_token)",
        "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)",
        "CREATE INDEX IF NOT EXISTS idx_users_session_token_hash ON users(session_token_hash)",
        "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_reviews_user_id ON reviews(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_repositories_user_id ON connected_repositories(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_api_keys_user_provider ON user_api_keys(user_id, provider)",
        "CREATE INDEX IF NOT EXISTS idx_webhook_events_repo_name ON webhook_events(repo_name)",
    ]

    for statement in statements:
        await conn.execute(text(statement))


async def _upgrade_neon_compat_tables(conn: AsyncConnection) -> None:
    dialect = conn.dialect.name
    bool_type = "BOOLEAN" if dialect != "sqlite" else "BOOLEAN"
    timestamp_type = "TIMESTAMPTZ" if dialect != "sqlite" else "TIMESTAMP"

    await conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS roles (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(32) UNIQUE NOT NULL,
                created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
            """
        )
    )

    await conn.execute(
        text(
            """
            INSERT INTO roles (id, name)
            VALUES ('role_admin', 'admin'), ('role_user', 'user')
            ON CONFLICT (name) DO NOTHING
            """
        )
    )

    await conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS api_keys (
                id VARCHAR(64) PRIMARY KEY,
                user_id VARCHAR NOT NULL,
                provider VARCHAR(20) NOT NULL,
                encrypted_key TEXT,
                is_active {bool_type} DEFAULT FALSE NOT NULL,
                created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
            """
        )
    )


def _assert_identifier(name: str) -> str:
    if not name or not name.replace("_", "").isalnum():
        raise ValueError(f"Unsafe SQL identifier: {name}")
    return name


def _build_null_safe_match_sql(left_alias: str, right_alias: str, columns: list[str]) -> str:
    parts: list[str] = []
    for column in columns:
        col = _assert_identifier(column)
        parts.append(
            f"(({left_alias}.{col} = {right_alias}.{col}) OR ({left_alias}.{col} IS NULL AND {right_alias}.{col} IS NULL))"
        )
    return " AND ".join(parts)


def _delete_user_id_update_conflicts_sync(sync_conn, inspector, table_name: str, keeper_id: str, duplicate_id: str) -> None:
    table = _assert_identifier(table_name)
    try:
        table_columns = {item["name"] for item in inspector.get_columns(table)}
    except Exception:
        return
    if "user_id" not in table_columns:
        return

    unique_sets: list[list[str]] = []
    for constraint in inspector.get_unique_constraints(table):
        cols = constraint.get("column_names") or []
        if cols:
            unique_sets.append([_assert_identifier(col) for col in cols])
    for index in inspector.get_indexes(table):
        if not index.get("unique"):
            continue
        cols = index.get("column_names") or []
        if cols:
            unique_sets.append([_assert_identifier(col) for col in cols])

    seen: set[tuple[str, ...]] = set()
    for cols in unique_sets:
        key = tuple(cols)
        if key in seen:
            continue
        seen.add(key)
        if "user_id" not in cols or len(cols) < 2:
            continue

        other_cols = [col for col in cols if col != "user_id"]
        if not other_cols:
            continue

        column_sql = _build_null_safe_match_sql("keeper", "target", other_cols)
        sync_conn.execute(
            text(
                f"""
                DELETE FROM {table} AS target
                WHERE target.user_id = :duplicate_id
                  AND EXISTS (
                    SELECT 1
                    FROM {table} AS keeper
                    WHERE keeper.user_id = :keeper_id
                      AND {column_sql}
                  )
                """
            ),
            {"keeper_id": keeper_id, "duplicate_id": duplicate_id},
        )


def _merge_duplicate_users_sync(sync_conn) -> None:
    inspector = inspect(sync_conn)
    try:
        tables = set(inspector.get_table_names())
    except Exception:
        return

    if "users" not in tables:
        return

    rows = sync_conn.execute(
        text(
            """
            SELECT
                id,
                github_id,
                email,
                username,
                role,
                auth_provider,
                avatar_url,
                access_token,
                session_token_hash,
                last_login_at,
                created_at
            FROM users
            ORDER BY
                CASE WHEN created_at IS NULL THEN 1 ELSE 0 END,
                created_at,
                id
            """
        )
    ).mappings().all()

    if not rows:
        return

    rows_by_id = {str(row["id"]): row for row in rows}
    ordered_ids = [str(row["id"]) for row in rows]
    order_index = {user_id: idx for idx, user_id in enumerate(ordered_ids)}

    parent = {user_id: user_id for user_id in ordered_ids}

    def _find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def _union(a: str, b: str) -> None:
        ra = _find(a)
        rb = _find(b)
        if ra != rb:
            if order_index[ra] <= order_index[rb]:
                parent[rb] = ra
            else:
                parent[ra] = rb

    duplicate_groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        user_id = str(row["id"])
        github_id = (row.get("github_id") or "").strip()
        if github_id:
            duplicate_groups[("github_id", github_id)].append(user_id)

        email_norm = (row.get("email") or "").strip().lower()
        if email_norm:
            duplicate_groups[("email", email_norm)].append(user_id)

    for ids in duplicate_groups.values():
        if len(ids) < 2:
            continue
        base = ids[0]
        for item in ids[1:]:
            _union(base, item)

    components: dict[str, list[str]] = defaultdict(list)
    for user_id in ordered_ids:
        components[_find(user_id)].append(user_id)

    merge_count = 0
    skipped_groups = 0
    for member_ids in components.values():
        if len(member_ids) < 2:
            continue

        members = [rows_by_id[user_id] for user_id in member_ids]
        has_admin_or_local = any(
            (str(row.get("role") or "").strip().lower() == "admin")
            or (str(row.get("auth_provider") or "").strip().lower() == "local")
            for row in members
        )
        if has_admin_or_local:
            skipped_groups += 1
            continue

        sorted_ids = sorted(member_ids, key=lambda uid: order_index[uid])
        keeper_id = sorted_ids[0]

        for duplicate_id in sorted_ids[1:]:
            duplicate = rows_by_id[duplicate_id]

            if "user_api_keys" in tables:
                _delete_user_id_update_conflicts_sync(sync_conn, inspector, "user_api_keys", keeper_id, duplicate_id)
                sync_conn.execute(
                    text("UPDATE user_api_keys SET user_id = :keeper_id WHERE user_id = :duplicate_id"),
                    {"keeper_id": keeper_id, "duplicate_id": duplicate_id},
                )
                user_api_key_columns = {item["name"] for item in inspector.get_columns("user_api_keys")}
                order_by = "is_active DESC, id DESC"
                if "updated_at" in user_api_key_columns:
                    order_by = "is_active DESC, updated_at DESC, id DESC"
                sync_conn.execute(
                    text(
                        f"""
                        UPDATE user_api_keys
                        SET is_active = CASE
                            WHEN id = (
                                SELECT id
                                FROM user_api_keys
                                WHERE user_id = :keeper_id
                                ORDER BY {order_by}
                                LIMIT 1
                            ) THEN 1 ELSE 0
                        END
                        WHERE user_id = :keeper_id
                        """
                    ),
                    {"keeper_id": keeper_id},
                )

            if "connected_repositories" in tables:
                _delete_user_id_update_conflicts_sync(
                    sync_conn,
                    inspector,
                    "connected_repositories",
                    keeper_id,
                    duplicate_id,
                )
                sync_conn.execute(
                    text("UPDATE connected_repositories SET user_id = :keeper_id WHERE user_id = :duplicate_id"),
                    {"keeper_id": keeper_id, "duplicate_id": duplicate_id},
                )

            if "sessions" in tables:
                _delete_user_id_update_conflicts_sync(sync_conn, inspector, "sessions", keeper_id, duplicate_id)
                sync_conn.execute(
                    text("UPDATE sessions SET user_id = :keeper_id WHERE user_id = :duplicate_id"),
                    {"keeper_id": keeper_id, "duplicate_id": duplicate_id},
                )

            if "reviews" in tables:
                _delete_user_id_update_conflicts_sync(sync_conn, inspector, "reviews", keeper_id, duplicate_id)
                sync_conn.execute(
                    text("UPDATE reviews SET user_id = :keeper_id WHERE user_id = :duplicate_id"),
                    {"keeper_id": keeper_id, "duplicate_id": duplicate_id},
                )

            if "api_keys" in tables:
                _delete_user_id_update_conflicts_sync(sync_conn, inspector, "api_keys", keeper_id, duplicate_id)
                sync_conn.execute(
                    text("UPDATE api_keys SET user_id = :keeper_id WHERE user_id = :duplicate_id"),
                    {"keeper_id": keeper_id, "duplicate_id": duplicate_id},
                )

            sync_conn.execute(
                text(
                    """
                    UPDATE users
                    SET
                        github_id = COALESCE(NULLIF(users.github_id, ''), :dup_github_id),
                        email = COALESCE(NULLIF(LOWER(TRIM(users.email)), ''), :dup_email),
                        avatar_url = COALESCE(NULLIF(users.avatar_url, ''), :dup_avatar_url),
                        access_token = CASE
                            WHEN COALESCE(NULLIF(users.access_token, ''), '') = '' THEN :dup_access_token
                            ELSE users.access_token
                        END,
                        session_token_hash = CASE
                            WHEN COALESCE(NULLIF(users.session_token_hash, ''), '') = '' THEN :dup_session_token_hash
                            ELSE users.session_token_hash
                        END,
                        last_login_at = COALESCE(users.last_login_at, :dup_last_login_at)
                    WHERE users.id = :keeper_id
                    """
                ),
                {
                    "keeper_id": keeper_id,
                    "dup_github_id": (duplicate.get("github_id") or "").strip() or None,
                    "dup_email": (duplicate.get("email") or "").strip().lower() or None,
                    "dup_avatar_url": duplicate.get("avatar_url"),
                    "dup_access_token": duplicate.get("access_token"),
                    "dup_session_token_hash": duplicate.get("session_token_hash"),
                    "dup_last_login_at": duplicate.get("last_login_at"),
                },
            )

            sync_conn.execute(
                text("DELETE FROM users WHERE id = :duplicate_id"),
                {"duplicate_id": duplicate_id},
            )
            merge_count += 1

    if merge_count:
        print(f"[MIGRATION] Merged {merge_count} duplicate user account(s).")
    if skipped_groups:
        print(f"[MIGRATION] Skipped {skipped_groups} duplicate group(s) containing admin/local users.")


def _enforce_user_identity_constraints_sync(sync_conn) -> None:
    inspector = inspect(sync_conn)
    sync_conn.execute(
        text(
            """
            UPDATE users
            SET github_id = NULLIF(TRIM(github_id), '')
            WHERE github_id IS NOT NULL
            """
        )
    )
    sync_conn.execute(
        text(
            """
            UPDATE users
            SET email = NULLIF(LOWER(TRIM(email)), '')
            WHERE email IS NOT NULL
            """
        )
    )

    rows = sync_conn.execute(
        text(
            """
            SELECT id, github_id, email
            FROM users
            ORDER BY
                CASE WHEN created_at IS NULL THEN 1 ELSE 0 END,
                created_at,
                id
            """
        )
    ).mappings().all()

    seen_github_ids: set[str] = set()
    seen_emails: set[str] = set()
    for row in rows:
        user_id = str(row["id"])

        github_id = (row.get("github_id") or "").strip()
        if github_id:
            if github_id in seen_github_ids:
                sync_conn.execute(
                    text("UPDATE users SET github_id = NULL WHERE id = :user_id"),
                    {"user_id": user_id},
                )
            else:
                seen_github_ids.add(github_id)

        email_norm = (row.get("email") or "").strip().lower()
        if email_norm:
            if email_norm in seen_emails:
                sync_conn.execute(
                    text("UPDATE users SET email = NULL WHERE id = :user_id"),
                    {"user_id": user_id},
                )
            else:
                seen_emails.add(email_norm)

    sync_conn.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_users_github_id_nonnull
            ON users (github_id)
            WHERE github_id IS NOT NULL
            """
        )
    )

    dialect = sync_conn.dialect.name
    supports_expression_index = dialect == "postgresql"
    if dialect == "sqlite":
        try:
            version_raw = str(sync_conn.execute(text("SELECT sqlite_version()")).scalar() or "0.0.0")
            parts = version_raw.split(".")
            major = int(parts[0]) if len(parts) > 0 else 0
            minor = int(parts[1]) if len(parts) > 1 else 0
            patch = int(parts[2]) if len(parts) > 2 else 0
            supports_expression_index = (major, minor, patch) >= (3, 9, 0)
        except Exception:
            supports_expression_index = False

    if supports_expression_index:
        sync_conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_ci_nonnull
                ON users (LOWER(email))
                WHERE email IS NOT NULL
                """
            )
        )
    else:
        has_plain_email_unique = False
        for constraint in inspector.get_unique_constraints("users"):
            cols = constraint.get("column_names") or []
            if cols == ["email"]:
                has_plain_email_unique = True
                break
        if not has_plain_email_unique:
            for index in inspector.get_indexes("users"):
                if index.get("unique") and (index.get("column_names") or []) == ["email"]:
                    has_plain_email_unique = True
                    break
        if not has_plain_email_unique:
            sync_conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_nonnull
                    ON users (email)
                    WHERE email IS NOT NULL
                    """
                )
            )


async def _upgrade_users_identity_integrity(conn: AsyncConnection) -> None:
    await conn.run_sync(_merge_duplicate_users_sync)
    await conn.run_sync(_enforce_user_identity_constraints_sync)


MIGRATIONS: list[Migration] = [
    Migration(name="0001_users_schema_sync", upgrade=_upgrade_users_schema),
    Migration(name="0002_indexes", upgrade=_upgrade_indexes),
    Migration(name="0003_auth_provider_split", upgrade=_upgrade_users_schema),
    Migration(name="0004_neon_compat_tables", upgrade=_upgrade_neon_compat_tables),
    Migration(name="0005_users_identity_integrity", upgrade=_upgrade_users_identity_integrity),
]


async def apply_pending_migrations(conn: AsyncConnection) -> None:
    await _ensure_migration_table(conn)

    rows = await conn.execute(text("SELECT name FROM schema_migrations"))
    applied = {row[0] for row in rows.fetchall()}

    for migration in MIGRATIONS:
        if migration.name in applied:
            continue
        await migration.upgrade(conn)
        await conn.execute(
            text("INSERT INTO schema_migrations (name) VALUES (:name)"),
            {"name": migration.name},
        )
