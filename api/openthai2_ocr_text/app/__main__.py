import logging

import uvicorn

from app.config import Settings

settings = Settings()
logger = logging.getLogger("openthai")
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)
logger.propagate = False
uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, workers=settings.workers,
            timeout_keep_alive=5, limit_concurrency=8, access_log=False)
