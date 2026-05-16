import uvicorn
from app.config import settings

if __name__ == "__main__":
    # In production, we use 4 workers for better concurrency.
    # In development, we use 1 worker with reload enabled for DX.
    is_prod = settings.ENVIRONMENT == "production"
    workers = 4 if is_prod else 1
    reload = not is_prod

    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=settings.PORT, 
        workers=workers, 
        reload=reload
    )
