import re
from datetime import date
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ROI(InputModel):
    x1: int = Field(ge=0, strict=True)
    y1: int = Field(ge=0, strict=True)
    x2: int = Field(gt=0, strict=True)
    y2: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def valid_bounds(self):
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("ROI must have positive width and height")
        return self


class TestCaseCreate(InputModel):
    document_id: UUID
    page_number: int | None = Field(default=None, ge=1, strict=True)
    roi: ROI | None = None
    ground_truth_raw: str | None = Field(default=None, max_length=100000)
    category_codes: list[str] = Field(default_factory=list, max_length=30)


class TestCaseUpdate(InputModel):
    roi: ROI | None = None
    ground_truth_raw: str | None = Field(default=None, max_length=100000)
    category_codes: list[str] | None = Field(default=None, max_length=30)


class GroundTruthUpdate(InputModel):
    ground_truth_raw: str = Field(max_length=100000)
    confirmed: bool = False


class RunRequest(InputModel):
    pipelines: list[Annotated[str, Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")]] = Field(min_length=1, max_length=100)

    @field_validator("pipelines")
    @classmethod
    def unique_pipelines(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Select each pipeline only once")
        return value


class BatchRequest(RunRequest):
    pages: list[int] = Field(min_length=1, max_length=5000)
    category_codes: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("pages", mode="before")
    @classmethod
    def valid_pages(cls, value):
        if not isinstance(value, list) or any(type(page) is not int or not 1 <= page <= 5000 for page in value):
            raise ValueError("Pages must be integers from 1 to 5000")
        return sorted(set(value))


class PipelineConfigUpdate(InputModel):
    name: str = Field(default="Pipeline", min_length=1, max_length=100)
    base_url: str = Field(default="", max_length=500)
    endpoint: str = Field(default="", max_length=500)
    http_method: Literal["POST"] = "POST"
    request_format: Literal["multipart", "json_base64"] = "multipart"
    file_field_name: Literal["image", "images"] = "image"
    enabled: bool = True
    engine: str | None = Field(default=None, max_length=100)
    include_roi: Literal[False] = False
    query_params: dict[str, str] = Field(default_factory=dict)

    @field_validator("query_params")
    @classmethod
    def validate_query(cls, value):
        if set(value) - {"engine", "version"}:
            raise ValueError("Only non-secret engine/version query parameters are supported")
        return value

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value):
        value = value.strip().rstrip("/")
        if value:
            parts = urlsplit(value)
            if parts.scheme not in {"http", "https"} or not parts.hostname:
                raise ValueError("Base URL must use HTTP or HTTPS")
            if parts.username or parts.password or parts.query or parts.fragment:
                raise ValueError(
                    "Base URL cannot contain credentials, query parameters, or fragments"
                )
        return value

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value):
        value = value.strip()
        if value and (
            not value.startswith("/")
            or value.startswith("//")
            or "?" in value
            or "#" in value
            or "\\" in value
        ):
            raise ValueError(
                "Endpoint must be a relative path beginning with / without query parameters"
            )
        return value

    @field_validator("file_field_name")
    @classmethod
    def validate_field_name(cls, value):
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_\-]*", value):
            raise ValueError("File field name must be a simple identifier")
        return value


class BenchmarkFilters(BaseModel):
    category: str | None = None
    pipeline: str | None = Field(default=None, max_length=50)
    date_from: date | None = None
    date_to: date | None = None
    document: UUID | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("Start date must be on or before end date")
        return self


class ROIUpdate(InputModel):
    roi: ROI | None


class CategoriesUpdate(InputModel):
    category_codes: list[str] = Field(max_length=30)


class AutoROIRequest(InputModel):
    page_number: int | None = Field(default=None, ge=1, strict=True)
    auto_roi_mode: Literal["text-line", "layout", "hybrid"] = "text-line"
    expand_text_rois: bool = False


class ErrorFilters(BaseModel):
    pipeline: str | None = Field(default=None, max_length=50)
    category: str | None = Field(default=None, max_length=50)
    error_type: Literal["substitution", "deletion", "insertion"] | None = None
    error_level: Literal["char", "word"] = "char"
    text_kind: Literal["raw", "final"] = "final"
    test_case_id: UUID | None = None
    document: UUID | None = None


class DatasetExport(InputModel):
    test_case_ids: list[UUID] = Field(min_length=1, max_length=200)

    @field_validator("test_case_ids")
    @classmethod
    def unique_ids(cls, ids):
        if len(ids) != len(set(ids)):
            raise ValueError("Select each sample only once")
        return ids
