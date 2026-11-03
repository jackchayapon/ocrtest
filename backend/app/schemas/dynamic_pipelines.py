import re
from typing import Literal
from urllib.parse import parse_qsl, unquote, urlsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.integrations.gateway_routes import safe_path
from app.schemas.contracts import InputModel


class OCRModelInput(InputModel):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["det", "rec"]
    source: Literal["custom", "official"]
    version: str = Field(min_length=1, max_length=50)
    weight: str = Field(default="default", min_length=1, max_length=100)
    single_path: str = Field(default="", max_length=500)
    batch_path: str = Field(min_length=1, max_length=500)

    @field_validator("name", "version", "weight")
    @classmethod
    def nonblank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Name, version and weight cannot be blank")
        return value

    @field_validator("single_path", "batch_path")
    @classmethod
    def safe_path(cls, value):
        value = value.strip()
        if not value:
            return value
        parts = urlsplit(value)
        decoded = unquote(parts.path)
        if (parts.scheme or parts.netloc or parts.fragment or not re.search(r"/api/v\d+/", parts.path)
                or "\\" in decoded or "//" in decoded or ".." in decoded.split("/")
                or any(ord(c) < 32 for c in value)):
            raise ValueError("Use a relative /api/ path without credentials or fragments")
        safe_path(parts.path)
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        if len({k for k, _ in pairs}) != len(pairs):
            raise ValueError("Duplicate query parameters are not supported")
        if any(k not in {"version", "model", "weight", "engine"} or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", v) for k, v in pairs):
            raise ValueError("Only non-secret version/model/weight/engine parameters are supported")
        return value

    @model_validator(mode="after")
    def batch_required(self):
        if not self.batch_path:
            raise ValueError("A batch API path is required")
        for path in (self.single_path, self.batch_path):
            if not path:
                continue
            params = dict(parse_qsl(urlsplit(path).query))
            if "version" in params and params["version"].removeprefix("v") != self.version.removeprefix("v"):
                raise ValueError("Version must match the version in API paths")
            if params.get("model", params.get("weight", "default")) != self.weight:
                raise ValueError("Weight must match the model/weight in API paths; use default when omitted")
        return self


class DynamicPipelineInput(InputModel):
    name: str = Field(min_length=1, max_length=100)
    source: Literal["custom", "official"]
    execution_mode: Literal["integrated", "det_rec", "rec"] = "integrated"
    det_model_id: UUID | None = None
    rec_model_id: UUID | None = None
    version: Literal["5", "6"] = "6"
    det_weight: str = Field(default="baseline", pattern=r"^[a-zA-Z0-9_.-]{1,100}$")
    rec_weight: str = Field(default="baseline", pattern=r"^[a-zA-Z0-9_.-]{1,100}$")
    paddle_model_defaults: bool = True
    det_version: Literal["5", "6"] | None = None
    rec_version: Literal["5", "6"] | None = None
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Pipeline name cannot be blank")
        return value.strip()

    @model_validator(mode="after")
    def stages(self):
        if self.source == "custom" and any(w not in {"baseline", "thai_ft_v1", "thai_ft_v2"} for w in (self.det_weight, self.rec_weight)):
            raise ValueError("Unsupported custom weight")
        if self.source == "official" and self.execution_mode == "integrated" and not self.paddle_model_defaults:
            if self.det_version is None or self.rec_version is None:
                raise ValueError("Select both DET and REC versions")
        if (self.execution_mode == "det_rec") != (self.det_model_id is not None):
            raise ValueError("Select a detection model only for DET + REC pipelines")
        if (self.execution_mode != "integrated") != (self.rec_model_id is not None):
            raise ValueError("Select a recognition model for separate DET/REC pipelines only")
        return self
