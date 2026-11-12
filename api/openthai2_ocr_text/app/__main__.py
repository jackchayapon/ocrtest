import uvicorn

from app.config import Settings

settings = Settings()
uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, workers=settings.workers,
            timeout_keep_alive=5, limit_concurrency=8, access_log=False)
