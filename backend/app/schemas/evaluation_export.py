from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.contracts import InputModel


class ExcelEvaluationSelection(InputModel):
    mode: Literal["per_field", "whole_document"]
    pipeline_ids: list[str] = Field(min_length=1, max_length=100)
    run_ids: list[UUID] = Field(min_length=1, max_length=100)
    field_ids: list[UUID] = Field(default_factory=list, max_length=2000)
    revision: datetime

    @model_validator(mode="after")
    def valid_selection(self):
        if len(self.pipeline_ids) != len(self.run_ids):
            raise ValueError("Pipeline/run selections must correspond")
        for values in (self.pipeline_ids, self.run_ids, self.field_ids):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate selection IDs")
        if any(not value or len(value) > 50 for value in self.pipeline_ids):
            raise ValueError("Invalid pipeline ID")
        if self.revision.tzinfo is None:
            raise ValueError("Revision must include timezone")
        if self.mode == "per_field" and not self.field_ids:
            raise ValueError("Select at least one field")
        if self.mode == "whole_document" and self.field_ids:
            raise ValueError("Whole document cannot include field selection")
        return self
