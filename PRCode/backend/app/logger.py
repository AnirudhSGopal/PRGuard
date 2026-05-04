import logging
import sys
import time
from fastapi import Request

# Configure central logger
logger = logging.getLogger("prguard")
logger.setLevel(logging.INFO)

# File handler
file_handler = logging.FileHandler("server_log.txt")
file_handler.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)

# Formatter
formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
file_handler.setFormatter(formatter)
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
        
        log_message = f"{request.method} {request.url.path} - HTTP {status_code} - {process_time:.2f}ms"
        
        # Log request and response times
        if status_code >= 500:
            logger.error(log_message)
        elif status_code >= 400:
            logger.warning(log_message)
        else:
            logger.info(log_message)
            
    return response

def log_ai_usage(provider: str, model: str, route: str, cache_hit: bool):
    """Log AI calls to monitor usage and token savings."""
    msg = f"AI Execution: Provider={provider}, Model={model}, Context={route}, CacheHit={cache_hit}"
    logger.info(msg)
