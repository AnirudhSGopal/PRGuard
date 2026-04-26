from pydantic import ConfigDict, field_validator, model_validator
from pydantic_settings import BaseSettings
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

BACKEND_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

class Settings(BaseSettings):
    model_config = ConfigDict(
        extra="ignore",
        env_file=(str(BACKEND_ENV_FILE),),
        env_ignore_empty=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (init_settings, env_settings, dotenv_settings, file_secret_settings)

    GITHUB_APP_ID: str = ""
    GITHUB_PRIVATE_KEY: str = ""
    GITHUB_WEBHOOK_SECRET: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    LLM_API_KEY: str = ""

    REDIS_URL: str = ""

    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "prguard"
    LANGCHAIN_TRACING_V2: str = "true"

    HTTP_TIMEOUT: int = 60
    DATABASE_URL: str = ""
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    DB_CONNECT_RETRIES: int = 3
    DB_CONNECT_TIMEOUT: int = 10
    DB_RETRY_DELAY_SECONDS: float = 0.5
    DB_MAX_RETRY_DELAY_SECONDS: float = 5.0
    FRONTEND_URL: str = ""
    APP_URL: str = ""
    API_BASE_URL: str = ""
    CORS_ORIGINS: str = ""
    ENV: str = ""
    NODE_ENV: str = ""
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    SECRET_KEY: str = ""
    JWT_SECRET: str = ""
    SESSION_SECRET: str = ""
    ADMIN_USERS: str = ""
    ADMIN_EMAIL: str = ""
    ADMIN_EMAILS: str = ""
    ADMIN_USERNAME: str = ""
    ADMIN_PASSWORD: str = ""
    ADMIN_SESSION_TTL_SECONDS: int = 60 * 60 * 12

    # ── LLM Unified Config ──
    MODEL_PROVIDER: str = "gemini" 
    MODEL_NAME: str = "gemini-2.5-flash"
    CHAT_ENABLE_RAG: bool = False
    PRELOAD_RAG_ON_STARTUP: bool = False

    @field_validator("DEBUG", mode="before")
    @classmethod
    def coerce_debug_value(cls, value):
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on", "debug"}:
            return True
        if normalized in {"0", "false", "no", "off", "warn", "warning", "info", "error"}:
            return False
        return False

    def has_any_llm_key(self) -> bool:
        return any([self.ANTHROPIC_API_KEY, self.OPENAI_API_KEY, self.GEMINI_API_KEY, self.LLM_API_KEY])

    @staticmethod
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

    @model_validator(mode="after")
    def validate_database_configuration(self):
        database_url = self.normalize_database_url((self.DATABASE_URL or "").strip())
        if not database_url:
            if self.is_development():
                database_url = "sqlite+aiosqlite:///./prguard.db"
            else:
                raise ValueError("DATABASE_URL must be set in the environment.")
        self.DATABASE_URL = database_url

        if self.is_development():
            if not (self.APP_URL or "").strip():
                self.APP_URL = "http://localhost:8000"
            if not (self.FRONTEND_URL or "").strip():
                self.FRONTEND_URL = "http://localhost:5173"

        # Compatibility fallback: if API_BASE_URL is omitted, reuse APP_URL.
        if not (self.API_BASE_URL or "").strip() and (self.APP_URL or "").strip():
            self.API_BASE_URL = self.APP_URL.strip()

        # Compatibility fallback for legacy single-key deployments.
        if (self.LLM_API_KEY or "").strip() and not any(
            [self.ANTHROPIC_API_KEY.strip(), self.OPENAI_API_KEY.strip(), self.GEMINI_API_KEY.strip()]
        ):
            provider = (self.MODEL_PROVIDER or "gemini").strip().lower()
            if provider in {"gpt", "openai"}:
                self.OPENAI_API_KEY = self.LLM_API_KEY.strip()
            elif provider in {"claude", "anthropic"}:
                self.ANTHROPIC_API_KEY = self.LLM_API_KEY.strip()
            else:
                self.GEMINI_API_KEY = self.LLM_API_KEY.strip()

        if not self.is_development():
            for field_name in ("APP_URL", "FRONTEND_URL", "API_BASE_URL"):
                raw_value = (getattr(self, field_name, "") or "").strip()
                if raw_value and not raw_value.lower().startswith("https://"):
                    raise ValueError(f"{field_name} must use HTTPS in non-development environments.")

            required_fields = {
                "APP_URL": self.APP_URL,
                "FRONTEND_URL": self.FRONTEND_URL,
                "SECRET_KEY": self.SECRET_KEY,
                "JWT_SECRET": self.JWT_SECRET,
                "GITHUB_CLIENT_ID": self.GITHUB_CLIENT_ID,
                "GITHUB_CLIENT_SECRET": self.GITHUB_CLIENT_SECRET,
                "GITHUB_WEBHOOK_SECRET": self.GITHUB_WEBHOOK_SECRET,
            }

            missing = [name for name, val in required_fields.items() if not (val or "").strip()]
            if missing:
                raise ValueError(
                    f"Missing required production environment variables: {', '.join(missing)}"
                )

            placeholder = [name for name, val in required_fields.items() if self._is_placeholder(val)]
            if placeholder:
                raise ValueError(
                    f"Placeholder values are not allowed for production environment variables: {', '.join(placeholder)}"
                )

            if self._is_placeholder(self.DATABASE_URL):
                raise ValueError("DATABASE_URL contains placeholder values and is not deployment-ready.")

            if not any(
                [
                    (self.OPENAI_API_KEY or "").strip(),
                    (self.ANTHROPIC_API_KEY or "").strip(),
                    (self.GEMINI_API_KEY or "").strip(),
                    (self.LLM_API_KEY or "").strip(),
                ]
            ):
                raise ValueError(
                    "At least one LLM API key must be configured in production "
                    "(OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, or LLM_API_KEY)."
                )

            for url_field in ("APP_URL", "FRONTEND_URL", "API_BASE_URL"):
                url_value = (getattr(self, url_field, "") or "").strip().lower()
                if "localhost" in url_value or "127.0.0.1" in url_value:
                    raise ValueError(f"{url_field} cannot point to localhost in production.")

        return self

    def normalize_database_url(self, database_url: str) -> str:
        value = (database_url or "").strip()
        if not value:
            return ""

        if value.startswith("postgres://"):
            value = "postgresql://" + value[len("postgres://") :]

        parsed = urlsplit(value)
        scheme = parsed.scheme
        if scheme.startswith("sqlite"):
            return value
        if scheme in {"postgresql", "postgres"}:
            scheme = "postgresql+asyncpg"
        elif scheme == "postgresql+psycopg2":
            scheme = "postgresql+asyncpg"

        query_items = parse_qsl(parsed.query, keep_blank_values=True)
        normalized_query: list[tuple[str, str]] = []
        has_ssl = False

        for key, raw_val in query_items:
            key_lower = key.lower()
            val = (raw_val or "").strip()

            if scheme == "postgresql+asyncpg" and key_lower == "sslmode":
                if not has_ssl:
                    normalized_query.append(("ssl", val or "require"))
                    has_ssl = True
                continue

            if scheme == "postgresql+asyncpg" and key_lower == "channel_binding":
                continue

            if key_lower == "ssl":
                has_ssl = True

            normalized_query.append((key, val))

        hostname = (parsed.hostname or "").lower()
        managed_hosts_requiring_ssl = ("supabase.co", "supabase.com", "neon.tech")
        if scheme == "postgresql+asyncpg" and any(host in hostname for host in managed_hosts_requiring_ssl) and not has_ssl:
            normalized_query.append(("ssl", "require"))

        query = urlencode(normalized_query, doseq=True)
        return urlunsplit((scheme, parsed.netloc, parsed.path, query, parsed.fragment))

    def is_development(self) -> bool:
        mode = (self.ENV or self.NODE_ENV or self.ENVIRONMENT or "development").strip().lower()
        return mode in {"development", "dev", "local"} or self.DEBUG

    def database_url(self) -> str:
        return self.normalize_database_url(self.DATABASE_URL)

    def database_host_summary(self) -> str:
        value = self.database_url()
        if not value:
            return "<missing>"

        parsed = urlsplit(value)
        if parsed.scheme.startswith("sqlite"):
            return value
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        username = f"{parsed.username}@" if parsed.username else ""
        netloc = f"{username}{host}{port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))

    def validate_secret_key(self) -> None:
        insecure_defaults = {"changeme", "changeme123"}
        is_development_mode = self.is_development()

        if not is_development_mode:
            if not self.SECRET_KEY:
                raise ValueError("SECRET_KEY must be explicitly set in non-development environments.")
            if self.SECRET_KEY in insecure_defaults:
                raise ValueError("Insecure SECRET_KEY configured for non-development environment.")

    def cors_origins(self) -> list[str]:
        configured = [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]
        defaults = [origin for origin in [self.FRONTEND_URL, self.APP_URL] if origin]

        origins = [origin for origin in configured + defaults if origin]
        return list(dict.fromkeys(origins))

    def admin_users_set(self) -> set[str]:
        return {
            user.strip().lower()
            for user in self.ADMIN_USERS.split(",")
            if user.strip()
        }

    def admin_emails_set(self) -> set[str]:
        explicit_admin_emails = {
            email.strip().lower()
            for email in self.ADMIN_EMAILS.split(",")
            if email.strip()
        }
        legacy_admin_email = (self.ADMIN_EMAIL or "").strip().lower()
        if legacy_admin_email:
            explicit_admin_emails.add(legacy_admin_email)
        return explicit_admin_emails

    def oauth_bootstrap_role(self, email: str = "") -> str:
        # OAuth never auto-grants admin unless a deliberate email whitelist is configured.
        email_normalized = (email or "").strip().lower()
        if email_normalized and email_normalized in self.admin_emails_set():
            return "admin"
        return "user"

    def is_admin_identity(self, login: str = "", email: str = "", role: str = "") -> bool:
        role_normalized = (role or "").strip().lower()
        if role_normalized == "admin":
            return True

        login_normalized = (login or "").strip().lower()
        email_normalized = (email or "").strip().lower()
        admin_email = (self.ADMIN_EMAIL or "").strip().lower()

        if login_normalized and login_normalized in self.admin_users_set():
            return True
        if admin_email and email_normalized and admin_email == email_normalized:
            return True
        return False

    @property
    def env_file_loaded(self) -> str:
        return str(BACKEND_ENV_FILE)

settings = Settings()
if not (settings.SECRET_KEY or "").strip():
    settings.SECRET_KEY = (settings.JWT_SECRET or settings.SESSION_SECRET or "").strip()
settings.validate_secret_key()