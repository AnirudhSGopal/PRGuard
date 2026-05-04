from __future__ import annotations

import hashlib
import secrets

import bcrypt


def hash_password(password: str) -> str:
    value = (password or "").encode("utf-8")
    return bcrypt.hashpw(value, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw((password or "").encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()
