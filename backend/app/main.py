import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import (
    activity,
    benchmark,
    dataset,
    document_types,
    documents,
    health,
    ocr_jobs,
    pipelines,
    test_cases,
)
from app.core.config import Settings
from app.core.errors import AppError
from app.core.workload import WorkloadGuard
from app.db.database import Database
from app.db.diagnostics import ReadStats, current_stats, install_diagnostics, log_stats
from app.db.seed import seed_database
from app.services.config_cache import ConfigCache, install_invalidation
from app.services.ocr_jobs import JobWorker
from app.services.storage_service import LocalStorageService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings)
    storage = LocalStorageService(settings.storage_path)
    config_cache = ConfigCache()
    install_invalidation(database.session_factory, config_cache)
    if settings.db_diagnostics:
        install_diagnostics(database.engine)

    @asynccontextmanager
    async def lifespan(app):
        try:
            database.migrate()
            with database.session_factory() as session:
                seed_database(session, settings)
        except Exception:
            raise RuntimeError(
                "Database initialization failed. Verify DATABASE_URL and migration access; credentials have been omitted."
            ) from None
        worker = JobWorker(database, settings, storage, app.state.ocr_lock, app.state.image_lock)
        app.state.job_worker = worker
        task = asyncio.create_task(worker.run()) if settings.ocr_jobs_enabled else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            database.engine.dispose()

    app = FastAPI(title="OCR Testing & Benchmark App", version="1.0.0", lifespan=lifespan)
    app.state.config_cache = config_cache
    app.state.database = database
    app.state.settings = settings
    app.state.storage = storage
    app.state.ocr_lock = asyncio.Lock()
    app.state.image_lock = asyncio.Lock()
    app.state.preview_read_lock = asyncio.Lock()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("app.integrations.model_gateway").setLevel(logging.INFO)

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        stats = ReadStats() if settings.db_diagnostics else None
        token = current_stats.set(stats) if stats else None
        try:
            response = await call_next(request)
        except Exception as exc:
            logging.getLogger(__name__).warning("api_unhandled_error category=%s", type(exc).__name__)
            response = JSONResponse({"detail": "The operation could not be completed."}, status_code=500)
        finally:
            if token is not None:
                current_stats.reset(token)
        if stats is not None:
            route = request.scope.get("route")
            log_stats(getattr(route, "path", "unmatched"), response.status_code, stats)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code,
                            headers={"Retry-After": "5"} if exc.status_code == 429 else None)

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def validation_error(request: Request, exc):
        # Pydantic's default error includes submitted input; avoid reflecting secrets and OCR text.
        errors = [
            {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return JSONResponse({"detail": errors}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc):
        return JSONResponse(
            {"detail": "Database operation failed. Check database availability."}, status_code=503
        )

    @app.exception_handler(Exception)
    async def unknown_error(request: Request, exc):
        return JSONResponse({"detail": "The operation could not be completed."}, status_code=500)

    for module in (health, documents, test_cases, ocr_jobs, pipelines, benchmark, activity, dataset, document_types):
        app.include_router(module.router, prefix="/api")
    # Outermost application middleware also covers sanitized application failures.
    # Railway-generated responses remain outside FastAPI's control.
    app.add_middleware(WorkloadGuard, lock=app.state.image_lock, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
        expose_headers=["Retry-After", "X-OCRLab-Retry-Safe"],
    )
    return app


app = create_app()
