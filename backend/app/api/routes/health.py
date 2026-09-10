from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.integrations.model_gateway import ModelGatewayClient

router = APIRouter()


@router.get("/upload-config")
def upload_config(request: Request):
    settings = request.app.state.settings
    return {"max_upload_mb": settings.max_upload_mb, "pdf_render_dpi": settings.pdf_render_dpi}


@router.get("/integrations/model-gateway/status")
async def gateway_status(request: Request):
    return await ModelGatewayClient(request.app.state.settings).status()


@router.get("/health")
def health(request: Request):
    database = request.app.state.database
    db_ok = False
    try:
        with database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    storage_ok = request.app.state.storage.healthy()
    return JSONResponse(
        {
            "status": "ok" if db_ok and storage_ok else "degraded",
            "database": {
                "status": "connected" if db_ok else "unavailable",
                "provider": database.engine.dialect.name,
                "mode": "development" if database.engine.dialect.name == "sqlite" else "postgresql",
            },
            "storage": {"status": "ready" if storage_ok else "unavailable", "mode": "local"},
            "version": "1.0.0",
        },
        status_code=200 if db_ok and storage_ok else 503,
    )
