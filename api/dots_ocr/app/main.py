import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.batch import infer_batch, infer_one, uploaded_files
from app.config import Settings
from app.errors import ServiceError, error_response
from app.inference import Inference
from app.security import RequestBoundary


def create_app(settings=None, loader=None):
    settings = settings or Settings()
    inference = Inference(settings, loader)

    @asynccontextmanager
    async def lifespan(app):
        try:
            await asyncio.get_running_loop().run_in_executor(
                inference.executor, inference.initialize
            )
            app.state.ready = True
        except Exception as error:
            app.state.ready = False
            app.state.load_error_type = type(error).__name__
            logging.getLogger("dots.startup").error(
                "model_load_failed category=%s", type(error).__name__
            )
        yield
        # A running native forward pass cannot safely be killed from a thread.
        app.state.ready = False
        await asyncio.get_running_loop().run_in_executor(
            inference.executor, inference.close
        )
        inference.executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(
        title="Standalone Dots OCR",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.ready = False
    app.state.settings = settings
    app.state.inference = inference
    app.add_middleware(RequestBoundary, settings=settings, inference=inference)

    @app.exception_handler(ServiceError)
    async def service_error(request, error):
        return error_response(error, request.state.request_id)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return error_response(
            ServiceError("INVALID_REQUEST", "Request validation failed."),
            request.state.request_id,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return error_response(
            ServiceError(
                "INVALID_REQUEST",
                "Request is not supported or malformed.",
                error.status_code,
            ),
            request.state.request_id,
        )

    def metadata(request):
        return {
            "api_version": "v1",
            "request_id": request.state.request_id,
            "model": settings.model_id,
            "revision": settings.revision,
            "backend": settings.backend,
            "device": getattr(inference.reader, "device", None),
            "dtype": getattr(inference.reader, "dtype", None),
        }

    @app.get("/health")
    async def health():
        return {"status": "alive"}

    @app.get("/api/v1/readiness")
    async def readiness(request: Request):
        return JSONResponse(
            {
                "ready": app.state.ready,
                "load_seconds": inference.load_seconds,
                "meta": metadata(request),
            },
            status_code=200 if app.state.ready else 503,
        )

    async def run(request, batch):
        if not app.state.ready:
            raise ServiceError("MODEL_NOT_READY", "Model is not ready.", 503)
        started = time.monotonic()
        contents = await uploaded_files(request, settings, batch)
        try:
            data = (
                await infer_batch(inference, contents, settings)
                if batch
                else await infer_one(inference, contents[0], settings)
            )
        except TimeoutError:
            raise ServiceError(
                "INFERENCE_TIMEOUT", "Model inference exceeded its deadline.", 504
            ) from None
        meta = metadata(request)
        meta["duration_ms"] = round((time.monotonic() - started) * 1000, 3)
        return {"data": data, "meta": meta}

    @app.post("/api/v1/ocr-text")
    async def single(request: Request):
        return await run(request, False)

    @app.post("/api/v1/ocr-text-batches")
    async def batch(request: Request):
        return await run(request, True)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=app.state.settings.host,
        port=app.state.settings.port,
        workers=1,
        access_log=False,
        ws="none",
    )
