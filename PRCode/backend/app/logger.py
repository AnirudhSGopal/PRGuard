import logging
import sys
import time
from pythonjsonlogger import jsonlogger
from fastapi import Request

# Configure central logger
logger = logging.getLogger("prguard")

from app.config import settings
# Use DEBUG toggle from config.py
log_level = logging.DEBUG if settings.DEBUG else logging.INFO
logger.setLevel(log_level)

# JSON formatter for production log aggregators
formatter = jsonlogger.JsonFormatter(
    '%(asctime)s %(levelname)s %(module)s %(message)s'
)

# File handler
file_handler = logging.FileHandler("server_log.txt")
file_handler.setLevel(log_level)
file_handler.setFormatter(formatter)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(log_level)
console_handler.setFormatter(formatter)

# Avoid duplicate attach
if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

async def log_request_middleware(request: Request, call_next):
    start_time = time.time()
    
    # Process request
    response = None
    try:
        response = await call_next(request)
    except Exception as e:
        logger.error(f"Unhandled Exception on {request.method} {request.url.path}: {str(e)}", exc_info=True)
        raise
    finally:
        process_time = (time.time() - start_time) * 1000
        status_code = response.status_code if response else 500
        
        log_data = {
            "method": request.method,
            "path": request.url.path,
            "status": status_code,
            "duration_ms": round(process_time, 2),
            "client_ip": request.client.host if request.client else "unknown"
        }
        
        if status_code >= 500:
            logger.error("request_failed", extra=log_data)
        elif status_code >= 400:
            logger.warning("request_warning", extra=log_data)
        else:
            logger.info("request_success", extra=log_data)
            
    return response

def log_ai_usage(provider: str, model: str, route: str, cache_hit: bool):
    """Log AI calls to monitor usage and token savings."""
    log_data = {
        "event": "ai_execution",
        "provider": provider,
        "model": model,
        "context": route,
        "cache_hit": cache_hit
    }
    logger.info("ai_usage", extra=log_data)
