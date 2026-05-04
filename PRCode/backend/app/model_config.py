import logging
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict

logger = logging.getLogger("prguard")

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
    Validates current active LLM configuration at startup.
    Throws visible error if critical keys are missing and no fallback exists.
    """
    primary = settings.MODEL_PROVIDER
    allow_user_keys = True
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
                logger.critical("FATAL: No LLM API keys found in environment!")
                raise RuntimeError("Startup failed: No LLM API keys available. Please set at least one provider key.")
        
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
    if not (settings.APP_URL or "").strip():
        missing_auth.append("APP_URL")
    if not (settings.FRONTEND_URL or "").strip():
        missing_auth.append("FRONTEND_URL")
    if not (settings.SECRET_KEY or "").strip():
        missing_auth.append("SECRET_KEY")

    if missing_auth:
        message = f"Auth environment is incomplete. Missing: {', '.join(missing_auth)}"
        if settings.is_development():
            logger.warning(message)
        else:
            logger.critical(message)
            raise RuntimeError(message)

