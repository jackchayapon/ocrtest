import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import Response
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from app.config import MODEL_REVISION, Settings
from app.errors import ServiceError, error_response
from app.inference import Inference
from app.security import RequestControls

logger = logging.getLogger("openthai")


def create_app(settings=None, loader=None):
    settings = settings or Settings()
    inference = Inference(settings, loader)

    @asynccontextmanager
    async def lifespan(app):
        try:
            await asyncio.get_running_loop().run_in_executor(inference.executor, inference.initialize)
        except Exception as error:
            logger.error("model_initialization_failed revision=%s category=%s", MODEL_REVISION, type(error).__name__)
        yield
        inference.executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(title="OpenThai OCR Text", version="1.0.0", lifespan=lifespan)
    app.state.inference = inference

    app.add_middleware(RequestControls, settings=settings, inference=inference)

    @app.exception_handler(ServiceError)
    async def service_error(request, error):
        return error_response(error, request.state.request_id)

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return error_response(ServiceError("BAD_REQUEST", "The HTTP request could not be accepted.", error.status_code), request.state.request_id)

    @app.get("/health")
    async def health():
        return {"status": "alive"}

    @app.get("/api/v1/readiness")
    async def readiness():
        if inference.reader is None:
            raise ServiceError("MODEL_NOT_READY", "The model is unavailable.", 503)
        return {"status": "ready", "model_revision": MODEL_REVISION}

    @app.post("/api/v1/ocr-text")
    async def ocr(request: Request):
        if inference.reader is None:
            raise ServiceError("MODEL_NOT_READY", "The model is unavailable.", 503)
        if not request.headers.get("content-type", "").startswith("multipart/form-data"):
            raise ServiceError("UNSUPPORTED_MEDIA_TYPE", "Use multipart/form-data.", 415)
        try:
            async with request.form(max_files=1, max_fields=0, max_part_size=settings.max_upload_bytes) as form:
                upload = form.get("image")
                if not isinstance(upload, UploadFile) or len(form) != 1:
                    raise ServiceError("IMAGE_REQUIRED", "Upload one file using the image field.")
                content = await upload.read(settings.max_upload_bytes + 1)
        except ServiceError:
            raise
        except (ValueError, RuntimeError, HTTPException):
            raise ServiceError("BAD_REQUEST", "Malformed multipart request.", 400) from None
        started = time.perf_counter()
        inference.pending = asyncio.get_running_loop().run_in_executor(inference.executor, inference.read, content)
        inference.pending.add_done_callback(lambda future: future.exception() if not future.cancelled() else None)
        # A deadline/disconnect never releases an actively running native model slot.
        data = await asyncio.shield(inference.pending)
        payload = {"data": data, "meta": {"request_id": request.state.request_id, "api_version": "v1",
                   "service": "openthai2-ocr-text", "model": "iapp/OpenThai2.0-OCR-Text",
                   "model_revision": MODEL_REVISION, "duration_ms": round((time.perf_counter()-started)*1000, 2)}}
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        if len(body) > settings.max_response_bytes:
            raise ServiceError("OUTPUT_TOO_LARGE", "Model output exceeds the response limit.", 503)
        return Response(body, media_type="application/json")

    return app


app = create_app()
