import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import benchmark, documents, health, pipelines, test_cases
from app.core.config import Settings
from app.core.errors import AppError
from app.db.database import Database
from app.db.seed import seed_database
from app.services.storage_service import LocalStorageService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings)
    storage = LocalStorageService(settings.storage_path)

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
        yield
        database.engine.dispose()

    app = FastAPI(title="OCR Testing & Benchmark App", version="1.0.0", lifespan=lifespan)
    app.state.database = database
    app.state.settings = settings
    app.state.storage = storage
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

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

    for module in (health, documents, test_cases, pipelines, benchmark):
        app.include_router(module.router, prefix="/api")
    return app


app = create_app()
