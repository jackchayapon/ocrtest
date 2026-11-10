from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import (
    MAX_DETECTION_REGIONS,
    MAX_JOB_FIELDS,
    MAX_JOB_PIPELINES,
    MAX_JOB_UNITS,
    MAX_OCR_TEXT_CHARACTERS,
)
from app.integrations.model_gateway import ModelGatewayClient

router = APIRouter()


@router.get("/upload-config")
def upload_config(request: Request):
    settings = request.app.state.settings
    return {"max_upload_mb": settings.max_upload_mb, "pdf_render_dpi": settings.pdf_render_dpi,
            "max_image_pixels": settings.max_image_pixels, "max_image_dimension": settings.max_image_dimension,
            "max_pdf_pages": settings.max_pdf_pages, "ocr_active_jobs": 1, "ocr_queue_capacity": 5,
            "max_job_fields": MAX_JOB_FIELDS, "max_job_pipelines": MAX_JOB_PIPELINES,
            "max_job_units": MAX_JOB_UNITS, "max_detection_regions": MAX_DETECTION_REGIONS,
            "max_ocr_text_characters": MAX_OCR_TEXT_CHARACTERS,
            "ocr_max_concurrent_fields": settings.ocr_max_concurrent_fields,
            "ocr_max_concurrent_tasks": settings.ocr_max_concurrent_tasks}


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
