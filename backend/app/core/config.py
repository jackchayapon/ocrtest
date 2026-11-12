from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Release ceiling; stale environment overrides must not bypass admission.
WORKLOAD_LIMITS = dict(max_upload_mb=10, max_image_pixels=2_000_000,
                       max_image_dimension=8000, max_pdf_pages=20,
                       model_gateway_max_response_mb=8, ocr_max_concurrent_tasks=1,
                       ocr_max_concurrent_fields=1, ocr_gateway_batch_size=1)
MAX_JOB_FIELDS = 80
MAX_JOB_PIPELINES = 3
MAX_JOB_UNITS = 240
MAX_DETECTION_REGIONS = 128
MAX_OCR_TEXT_CHARACTERS = 32768


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT.parent / ".env", BACKEND_ROOT / ".env"),
        extra="ignore",
    )
    db_diagnostics: bool = False
    database_url: SecretStr = SecretStr("")
    storage_mode: Literal["local"] = "local"
    storage_path: Path = BACKEND_ROOT / "storage" / "uploads"
    max_upload_mb: int = Field(default=10, ge=1, le=100)
    max_image_pixels: int = Field(default=2_000_000, ge=1)
    max_image_dimension: int = Field(default=8000, ge=1)
    pdf_render_dpi: int = Field(default=140, ge=72, le=400)
    max_pdf_pages: int = Field(default=20, ge=1, le=5000)
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    model_gateway_base_url: str = "http://107.129.186.30:62051"
    # Optional same-origin API prefixes, independently verified per service.
    model_gateway_service_prefixes: dict[str, str | None] = Field(default_factory=dict)
    model_gateway_api_key: SecretStr = SecretStr("")
    model_gateway_timeout_seconds: float = Field(default=240, gt=0, le=600)
    model_gateway_max_response_mb: int = Field(default=8, ge=1, le=256)
    ocr_max_concurrent_tasks: int = Field(default=1, ge=1, le=8)
    ocr_max_concurrent_fields: int = Field(default=1, ge=1, le=8)
    ocr_gateway_batch_size: int = Field(default=1, ge=1, le=30)
    ocr_jobs_enabled: bool = True
    external_ocr_providers: SecretStr = SecretStr("{}")
    external_ocr_development: bool = False
    mint_ocr_endpoint: str = "/api/v1/ocr-results"
    mint_ocr_engine: str = "custom"
    hutch_crop_endpoint: str = "/api/v1/ocr-results"
    hutch_crop_engine: str = "paddle"
    hutch_full_endpoint: str = ""

    @model_validator(mode="after")
    def release_ceiling(self):
        for name, ceiling in WORKLOAD_LIMITS.items():
            setattr(self, name, min(getattr(self, name), ceiling))
        return self

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url.get_secret_value().strip()
        if not url:
            # Native development fallback matches Compose; Neon is selected by DATABASE_URL.
            # SQLite is used only by isolated tests with an explicit URL.
            return "postgresql+psycopg://ocr:ocr_local_dev@127.0.0.1:5432/ocr_benchmark"
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    def api_key(self, pipeline_id: str) -> str:
        """All benchmark pipelines use the one public Gateway credential."""
        return self.model_gateway_api_key.get_secret_value()
