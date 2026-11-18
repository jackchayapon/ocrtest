import json
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
MODELS = json.loads((ROOT / "model-manifest.json").read_text())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DOTS_", env_file=ROOT / ".env", extra="ignore"
    )
    model_id: Literal["dots-studio/dots.ocr", "dots-studio/dots.mocr"] = (
        "dots-studio/dots.ocr"
    )
    model_root: Path = ROOT / "models"
    backend: Literal["transformers", "vllm"] = "transformers"
    device: str = Field(default="auto", pattern=r"^(auto|cpu|cuda(?::[0-9]+)?)$")
    dtype: Literal["auto", "float32", "float16", "bfloat16"] = "auto"
    attention: Literal["eager", "sdpa", "flash_attention_2"] = "sdpa"
    api_key: SecretStr = SecretStr("")
    host: str = "0.0.0.0"
    port: int = Field(default=8092, ge=1, le=65535)
    cpu_threads: int = Field(default=4, ge=1, le=32)
    max_upload_bytes: int = Field(default=10 * 1024**2, ge=1024, le=40 * 1024**2)
    max_pixels: int = Field(default=4_000_000, ge=3136, le=16_000_000)
    max_dimension: int = Field(default=8000, ge=56, le=16000)
    model_max_pixels: int = Field(default=1_003_520, ge=3136, le=4_000_000)
    max_new_tokens: int = Field(default=4096, ge=128, le=16384)
    max_response_bytes: int = Field(default=8 * 1024**2, ge=1024, le=32 * 1024**2)
    max_batch_images: int = Field(default=8, ge=1, le=16)
    max_batch_upload_bytes: int = Field(default=40 * 1024**2, ge=1024, le=160 * 1024**2)
    max_batch_response_bytes: int = Field(
        default=16 * 1024**2, ge=1024, le=64 * 1024**2
    )
    inference_timeout_seconds: float = Field(default=120, gt=0, le=600)
    request_timeout_seconds: float = Field(default=130, gt=0, le=900)
    batch_timeout_seconds: float = Field(default=600, gt=0, le=1800)
    gpu_memory_utilization: float = Field(default=0.7, ge=0.1, le=0.95)

    @property
    def revision(self):
        return MODELS[self.model_id]["revision"]

    @property
    def model_dir(self):
        return self.model_root / MODELS[self.model_id]["directory"]
