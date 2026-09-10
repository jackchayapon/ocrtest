from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT.parent / ".env", BACKEND_ROOT / ".env"),
        extra="ignore",
    )
    database_url: SecretStr = SecretStr("")
    storage_mode: Literal["local"] = "local"
    storage_path: Path = BACKEND_ROOT / "storage" / "uploads"
    max_upload_mb: int = Field(default=20, ge=1, le=100)
    max_image_pixels: int = Field(default=40_000_000, ge=1)
    max_image_dimension: int = Field(default=20000, ge=1)
    pdf_render_dpi: int = Field(default=200, ge=72, le=400)
    max_pdf_pages: int = Field(default=500, ge=1, le=5000)
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    model_gateway_base_url: str = "http://107.129.186.30:62051"
    model_gateway_api_key: SecretStr = SecretStr("")
    model_gateway_timeout_seconds: float = Field(default=240, gt=0, le=600)
    mint_gateway_base_url: str = ""
    mint_ocr_endpoint: str = "/api/v1/ocr-results"
    mint_ocr_engine: str = "custom"
    mint_api_key: SecretStr = SecretStr("")
    hutch_gateway_base_url: str = ""
    hutch_crop_endpoint: str = "/api/v1/ocr-results"
    hutch_crop_engine: str = "paddle"
    hutch_api_key: SecretStr = SecretStr("")
    hutch_full_base_url: str = ""
    hutch_full_endpoint: str = ""
    hutch_full_api_key: SecretStr = SecretStr("")

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
        shared_key = self.model_gateway_api_key.get_secret_value()
        if shared_key:
            return shared_key
        return {
            "mint": self.mint_api_key,
            "hutch_crop": self.hutch_api_key,
            "hutch_full": self.hutch_full_api_key,
        }[pipeline_id].get_secret_value()
