import base64
import binascii
import hashlib
import logging

from app.config import settings

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover - runtime fallback when wheels are unavailable
    Fernet = None
    class InvalidToken(Exception):
        pass


logger = logging.getLogger("prguard")
_FALLBACK_SECRET = "fallback-secret"
_xor_warning_emitted = False


def _secret_seed() -> str:
    secret = (settings.SECRET_KEY or "").strip()
    if secret:
        return secret

    if not settings.is_development():
        raise ValueError("SECRET_KEY must be set in non-development environments.")

    logger.warning("SECRET_KEY is not set; using development fallback seed. Configure SECRET_KEY for secure encryption.")
    return _FALLBACK_SECRET


def _fernet():
    # Derive a stable 32-byte key from SECRET_KEY for reversible encryption at rest.
    digest = hashlib.sha256(_secret_seed().encode("utf-8")).digest()
    if Fernet is None:
        return None
    return Fernet(base64.urlsafe_b64encode(digest))


def _xor_cipher(value: str) -> str:
    """Development-only insecure fallback used when Fernet/cryptography is unavailable."""
    global _xor_warning_emitted
    if not settings.is_development():
        raise ValueError("Insecure XOR fallback is not allowed in non-development environments.")
    if not _xor_warning_emitted:
        logger.warning(
            "Using insecure fallback in _xor_cipher/_xor_decipher because Fernet/cryptography is unavailable. "
            "Install cryptography wheels to restore secure encryption."
        )
        _xor_warning_emitted = True
    secret = hashlib.sha256(_secret_seed().encode("utf-8")).digest()
    raw = value.encode("utf-8")
    mixed = bytes(byte ^ secret[i % len(secret)] for i, byte in enumerate(raw))
    return base64.urlsafe_b64encode(mixed).decode("utf-8")


def _xor_decipher(value: str) -> str:
    """Development-only insecure fallback used when Fernet/cryptography is unavailable."""
    global _xor_warning_emitted
    if not settings.is_development():
        raise ValueError("Insecure XOR fallback is not allowed in non-development environments.")
    if not _xor_warning_emitted:
        logger.warning(
            "Using insecure fallback in _xor_cipher/_xor_decipher because Fernet/cryptography is unavailable. "
            "Install cryptography wheels to restore secure encryption."
        )
        _xor_warning_emitted = True
    secret = hashlib.sha256(_secret_seed().encode("utf-8")).digest()
    mixed = base64.urlsafe_b64decode(value.encode("utf-8"))
    raw = bytes(byte ^ secret[i % len(secret)] for i, byte in enumerate(mixed))
    return raw.decode("utf-8")


def encrypt_secret(raw_value: str) -> str:
    if not raw_value:
        return ""
    cipher = _fernet()
    if cipher is None:
        return _xor_cipher(raw_value)
    return cipher.encrypt(raw_value.encode("utf-8")).decode("utf-8")


def decrypt_secret(encrypted_value: str) -> str:
    if not encrypted_value:
        return ""
    try:
        cipher = _fernet()
        if cipher is None:
            return _xor_decipher(encrypted_value)
        return cipher.decrypt(encrypted_value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Failed to decrypt secret payload") from exc
