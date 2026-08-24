from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import re
from threading import Lock
from typing import Any

_state_lock = Lock()
_recent_chat_logs: deque[dict[str, Any]] = deque(maxlen=100)
_user_activity: dict[str, dict[str, Any]] = {}
_api_key_status: dict[str, dict[str, Any]] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_api_key(api_key: str) -> str:
    if not api_key:
        return "missing"
    key = api_key.strip()
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]}"


def record_user_activity(user_id: str, username: str) -> None:
    with _state_lock:
        _user_activity[user_id] = {
            "user_id": user_id,
            "username": username,
            "last_activity": _utc_now_iso(),
            "login_status": "active",
        }


def record_api_key_status(
    *,
    user_id: str,
    username: str,
    provider: str,
    api_key_present: bool,
    validation_result: str,
) -> None:
    with _state_lock:
        _api_key_status[user_id] = {
            "user_id": user_id,
            "username": username,
            "provider": provider,
            "status": "added" if api_key_present else "missing",
            "masked_key": "configured" if api_key_present else "missing",
            "validation_result": validation_result,
            "updated_at": _utc_now_iso(),
        }


def sanitize_error(error: str, max_len: int = 200) -> str:
    raw = (error or "").strip()
    if not raw:
        return ""

    sanitized = raw
    # Redact bearer tokens and API-key-like secrets.
    sanitized = re.sub(r"(?i)bearer\s+[a-z0-9._\-]+", "Bearer [REDACTED]", sanitized)
    sanitized = re.sub(r"(?i)\b(sk-[a-z0-9\-_]+)\b", "[REDACTED_KEY]", sanitized)
    sanitized = re.sub(r"(?i)\b(sk-ant-[a-z0-9\-_]+)\b", "[REDACTED_KEY]", sanitized)
    sanitized = re.sub(r"\bAIza[0-9A-Za-z\-_]{10,}\b", "[REDACTED_KEY]", sanitized)
    # Redact absolute file paths.
    sanitized = re.sub(r"[A-Za-z]:\\[^\s\"']+", "[REDACTED_PATH]", sanitized)
    sanitized = re.sub(r"/[^\s\"']+", "[REDACTED_PATH]", sanitized)

    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    if not sanitized:
        return "Error redacted"
    if len(sanitized) > max_len:
        sanitized = sanitized[: max_len - 3].rstrip() + "..."
    return sanitized


def record_chat_log(
    *,
    user_id: str,
    username: str,
    repo: str,
    provider: str,
    success: bool,
    error: str = "",
) -> None:
    safe_error = sanitize_error(error)
    with _state_lock:
        _recent_chat_logs.appendleft(
            {
                "timestamp": _utc_now_iso(),
                "user_id": user_id,
                "username": username,
                "repo": repo,
                "provider": provider,
                "status": "success" if success else "failure",
                "error": safe_error,
            }
        )


def get_user_activity() -> list[dict[str, Any]]:
    with _state_lock:
        return list(_user_activity.values())


def get_api_key_status() -> list[dict[str, Any]]:
    with _state_lock:
        return list(_api_key_status.values())


def get_recent_chat_logs(limit: int = 25) -> list[dict[str, Any]]:
    with _state_lock:
        return list(_recent_chat_logs)[:limit]
