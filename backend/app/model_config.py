import logging
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict

logger = logging.getLogger("prguard")


def _is_placeholder(value: str) -> bool:
    raw = (value or "").strip().lower()
    if not raw:
        return True

    placeholder_tokens = (
        "<",
        "your_",
        "your-",
        "replace",
        "example.com",
        "yourdomain.com",
        "changeme",
        "password",
    )
    return any(token in raw for token in placeholder_tokens)

class LLMConfig(BaseModel):
    """
    Principal Architect's Unified Model Configuration.
    Ensures that mismatched keys/providers are caught during instantiation.
    """
    provider: str = Field(..., description="LLM Provider (gemini, claude, gpt)")
    model_name: str = Field(..., description="Specific model version")
    api_key: str = Field(..., description="API Key for the provider")

    @validator("provider")
    def validate_provider(cls, v):
        allowed = ["gemini", "claude", "gpt"]
        if v.lower() not in allowed:
            raise ValueError(f"Provider must be one of {allowed}")
        return v.lower()

    @validator("api_key")
    def validate_key(cls, v, values):
        if not v or len(v) < 10:
            provider = values.get("provider", "unknown")
            raise ValueError(f"Critical: Missing or invalid API Key for {provider}")
        return v

def validate_environment(settings):
    """
    Validates core application environment at startup.
    The runtime can fall back to user-provided API keys, so a missing global LLM key
    should warn in production rather than block startup.
    """
    primary = settings.MODEL_PROVIDER
    allow_user_keys = settings.is_development()
    logger.info(f"System: Validating primary provider '{primary}'...")
    
    key_map = {
        "claude": settings.ANTHROPIC_API_KEY,
        "gpt":    settings.OPENAI_API_KEY,
        "gemini": settings.GEMINI_API_KEY,
    }
    
    active_key = key_map.get(primary)
    if not active_key:
        logger.warning(f"Primary provider '{primary}' selected but API key is missing. Checking fallbacks...")
        if not settings.has_any_llm_key():
            if allow_user_keys:
                logger.warning(
                    "No global LLM API keys found in environment. "
                    "Per-user API keys will be required at runtime."
                )
                active_key = None
            else:
                logger.warning(
                    "No global LLM API keys found in production. "
                    "PRGuard will rely on user-provided API keys at runtime."
                )
                active_key = None
        
        # Find first available key
        if settings.has_any_llm_key():
            for provider, key in key_map.items():
                if key:
                    logger.info(f"Using fallback provider: '{provider}'")
                    settings.MODEL_PROVIDER = provider
                    break
    else:
        logger.info(f"System: Provider '{primary}' validated successfully.")

    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        logger.warning("GitHub OAuth credentials missing. OAuth flows will fail.")

    missing_auth = []
    if not (settings.GITHUB_CLIENT_ID or "").strip():
        missing_auth.append("GITHUB_CLIENT_ID")
    if not (settings.GITHUB_CLIENT_SECRET or "").strip():
        missing_auth.append("GITHUB_CLIENT_SECRET")
    if not (settings.GITHUB_WEBHOOK_SECRET or "").strip():
        missing_auth.append("GITHUB_WEBHOOK_SECRET")
    if not (settings.APP_URL or "").strip():
        missing_auth.append("APP_URL")
    if not (settings.FRONTEND_URL or "").strip():
        missing_auth.append("FRONTEND_URL")
    if not (settings.SECRET_KEY or "").strip():
        missing_auth.append("SECRET_KEY")
    if not (settings.JWT_SECRET or "").strip():
        missing_auth.append("JWT_SECRET")

    if missing_auth:
        message = f"Auth environment is incomplete. Missing: {', '.join(missing_auth)}"
        if settings.ENVIRONMENT == "development":
            logger.warning(message)
        else:
            logger.critical(message)
            raise RuntimeError(message)

    if settings.ENVIRONMENT == "production":
        placeholder_fields = {
            "DATABASE_URL": settings.DATABASE_URL,
            "APP_URL": settings.APP_URL,
            "FRONTEND_URL": settings.FRONTEND_URL,
            "SECRET_KEY": settings.SECRET_KEY,
            "JWT_SECRET": settings.JWT_SECRET,
            "GITHUB_CLIENT_ID": settings.GITHUB_CLIENT_ID,
            "GITHUB_CLIENT_SECRET": settings.GITHUB_CLIENT_SECRET,
            "GITHUB_WEBHOOK_SECRET": settings.GITHUB_WEBHOOK_SECRET,
        }
        invalid = [name for name, val in placeholder_fields.items() if _is_placeholder(val)]
        if invalid:
            raise RuntimeError(
                "Production environment has placeholder values for: "
                + ", ".join(invalid)
            )

        for field_name in ("APP_URL", "FRONTEND_URL"):
            current = (getattr(settings, field_name, "") or "").strip().lower()
            if "localhost" in current or "127.0.0.1" in current:
                raise RuntimeError(f"{field_name} cannot target localhost in production.")

    if not settings.has_any_llm_key():
        message = (
            "At least one LLM API key is required via OPENAI_API_KEY, ANTHROPIC_API_KEY, "
            "or GEMINI_API_KEY."
        )
        if settings.ENVIRONMENT == "development":
            logger.warning(message)
        else:
            raise RuntimeError(message)


