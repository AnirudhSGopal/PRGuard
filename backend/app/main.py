from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.routes import webhook, auth, dashboard, chat, admin, user
from app.config import settings
from app.models import init_db

app = FastAPI(
    title="PRGuard", description="Codebase Learning Assistant", version="1.0.0"
)

logger = logging.getLogger("prguard")

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": str(exc.detail),
            "error": str(exc.detail),
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation error",
            "details": str(exc),
        },
    )

from app.middleware import GlobalHardenMiddleware, AdminRoleMiddleware
from app.logger import log_request_middleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.models.base import AsyncSessionLocal
from app.services.admin_bootstrap import ensure_default_admin
from app.models.base import ping_database

app.add_middleware(BaseHTTPMiddleware, dispatch=log_request_middleware)
app.add_middleware(GlobalHardenMiddleware)
app.add_middleware(AdminRoleMiddleware)

if settings.ENVIRONMENT == "development":
    allow_origins = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        settings.FRONTEND_URL,
    ]
else:
    allow_origins = [
        settings.FRONTEND_URL,
    ]

cors_kwargs = {
    "allow_origins": allow_origins,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}

app.add_middleware(CORSMiddleware, **cors_kwargs)

app.include_router(webhook.router, prefix="/webhook", tags=["webhook"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(user.router, prefix="/user", tags=["user"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])


def _log_runtime_wiring() -> None:
    logger.info("runtime_entrypoint module=app.main")
    logger.info("runtime_router_sources auth=app.routes.auth admin=app.routes.admin user=app.routes.user dashboard=app.routes.dashboard chat=app.routes.chat webhook=app.routes.webhook")

    middleware_chain = [m.cls.__name__ for m in app.user_middleware]
    logger.info("runtime_middleware_chain=%s", " -> ".join(middleware_chain))

    registered_routes: list[str] = []
    for route in app.routes:
        methods = ",".join(sorted(getattr(route, "methods", []) or []))
        path = getattr(route, "path", "")
        name = getattr(route, "name", "")
        if path:
            registered_routes.append(f"{methods} {path} ({name})")

    logger.info("runtime_routes_count=%s", len(registered_routes))
    for item in sorted(registered_routes):
        logger.info("runtime_route %s", item)


@app.on_event("startup")
async def startup():
    from app.model_config import validate_environment

    try:
        print("=" * 60)
        print("[STARTUP] Starting PRGuard backend...")
        print("=" * 60)
        print(f"[STARTUP] ENV FILE LOADED: {settings.env_file_loaded}")

        # ── Print all env vars (mask sensitive values) ──
        def _mask(val: str) -> str:
            v = (val or "").strip()
            if not v:
                return "<empty>"
            if len(v) <= 8:
                return "***"
            return f"{v[:6]}...{v[-4:]}"

        print("[STARTUP] -- Environment Configuration --")
        print(f"  ENVIRONMENT:        {settings.ENVIRONMENT}")
        print(f"  PORT:               {settings.PORT}")
        print(f"  DATABASE_URL:       {settings.database_host_summary()}")
        print(f"  APP_URL:            {settings.APP_URL}")
        print(f"  FRONTEND_URL:       {settings.FRONTEND_URL}")
        print(f"  SECRET_KEY:         {_mask(settings.SECRET_KEY)}")
        print(f"  JWT_SECRET:         {_mask(settings.JWT_SECRET)}")
        print(f"  GITHUB_CLIENT_ID:   {_mask(settings.GITHUB_CLIENT_ID)}")
        print(f"  GITHUB_CLIENT_SECRET: {_mask(settings.GITHUB_CLIENT_SECRET)}")
        print("[STARTUP] -- LLM Provider Keys --")
        print(f"  ANTHROPIC_API_KEY:  {_mask(settings.ANTHROPIC_API_KEY)}")
        print(f"  OPENAI_API_KEY:     {_mask(settings.OPENAI_API_KEY)}")
        print(f"  GEMINI_API_KEY:     {_mask(settings.GEMINI_API_KEY)}")
        print(f"  LLM_API_KEY:        {_mask(settings.LLM_API_KEY)}")
        print(f"  MODEL_PROVIDER:     {settings.MODEL_PROVIDER}")
        print(f"  MODEL_NAME:         {settings.MODEL_NAME}")
        print("[STARTUP] -- Feature Flags --")
        print(f"  CHAT_ENABLE_RAG:    {settings.CHAT_ENABLE_RAG}")
        print(f"  PRELOAD_RAG_ON_STARTUP: {settings.PRELOAD_RAG_ON_STARTUP}")
        print("=" * 60)

        # 1. Validate Core Application Environment
        print("[STARTUP] Validating environment...")
        validate_environment(settings)
        print("[STARTUP] Environment validation complete.")

        # 2. Init Database
        print(f"[STARTUP] Initializing database at {settings.database_host_summary()}...")
        await init_db()
        print("[STARTUP] DATABASE connected successfully [OK]")

        # 3. Bootstrap admin user for password-based admin login (optional).
        async with AsyncSessionLocal() as db:
            await ensure_default_admin(db)
        print("[STARTUP] Admin bootstrap complete.")

        # 4. RAG initialization is handled lazily or via migrations
        print(f"[STARTUP] RAG subsystem ready (pgvector). CHAT_ENABLE_RAG={settings.CHAT_ENABLE_RAG}")

        print("=" * 60)
        print("[STARTUP] PRGuard backend started successfully [OK]")
        print("=" * 60)
        _log_runtime_wiring()
    except Exception as e:
        print(f"[CRITICAL] System startup failed: {e}")
        # In production, we exit. In dev, we might allow limited mode.
        if settings.ENVIRONMENT == "production":
            import sys

            sys.exit(1)
        print("[WARN] System running in degraded mode.")


@app.get("/")
async def root():
    return {
        "status": "ok", 
        "message": "PRGuard API is running", 
        "version": "1.0.0",
        "docs_url": "/docs"
    }


@app.get("/health")
async def health(response: Response):
    required_env_loaded = bool(settings.DATABASE_URL and settings.SECRET_KEY)
    llm_key_configured = settings.has_any_llm_key()
    database_connected = False
    database_error = None


    try:
        await ping_database()
        database_connected = True
    except Exception as exc:
        database_error = str(exc)
        response.status_code = 503

    return {
        "status": "ok" if database_connected else "degraded",
        "service": "PRGuard",
        "database_url_configured": required_env_loaded,
        "database_connected": database_connected,
        "database_target": settings.database_host_summary(),
        "database_error": database_error,
        "llm_key_configured": llm_key_configured,
        "env_loaded": required_env_loaded,
    }


@app.get("/health/db")
async def health_db(response: Response):
    try:
        await ping_database()
        logger.info("DB health check passed: %s", settings.database_host_summary())
        return {
            "status": "ok",
            "database_connected": True,
            "database_target": settings.database_host_summary(),
        }
    except Exception as exc:
        logger.error("DB health check failed: %s", exc)
        response.status_code = 503
        return {
            "status": "error",
            "database_connected": False,
            "database_target": settings.database_host_summary(),
            "error": str(exc),
        }
