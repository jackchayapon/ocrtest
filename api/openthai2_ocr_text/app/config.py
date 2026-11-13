from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

MODEL_REVISION = "39fa41bdd49f067ba41b1d9de79c06ab506d67d4"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENTHAI_", env_file=".env", extra="ignore")
    model_dir: Path = Path("models/openthai2")
    api_key: SecretStr = SecretStr("")
    port: int = Field(default=8091, ge=1, le=65535)
    threads: int = Field(default=1, ge=1, le=8)
    workers: int = Field(default=1, ge=1, le=1)
    max_upload_bytes: int = Field(default=10 * 1024**2, ge=1, le=20 * 1024**2)
    max_pixels: int = Field(default=2_000_000, ge=1, le=40_000_000)
    max_dimension: int = Field(default=8000, ge=1, le=12000)
    max_response_bytes: int = Field(default=2 * 1024**2, ge=1024, le=8 * 1024**2)
    request_timeout_seconds: float = Field(default=120, gt=0, le=600)
    max_batch_images: int = Field(default=8, ge=1, le=16)
    max_batch_upload_bytes: int = Field(default=20 * 1024**2, ge=1, le=80 * 1024**2)
    max_batch_response_bytes: int = Field(default=8 * 1024**2, ge=1024, le=16 * 1024**2)
    batch_timeout_seconds: float = Field(default=120, gt=0, le=600)
    max_concurrent_batch_requests: int = Field(default=1, ge=0, le=1)
