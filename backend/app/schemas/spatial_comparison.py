from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.contracts import InputModel, ROI


class SpatialReference(InputModel):
    id: str = Field(min_length=1, max_length=100)
    roi: ROI | None
    text: str = Field(max_length=10000)


class SpatialOverride(InputModel):
    box_id: str = Field(max_length=100)
    reference_id: str | None


class SpatialComparison(InputModel):
    run_id: UUID
    references: list[SpatialReference] = Field(min_length=1, max_length=128)
    overrides: list[SpatialOverride] = Field(default_factory=list, max_length=128)
    confirmed_gt: bool = False
    text_only: bool = False

    @model_validator(mode="after")
    def bounded_unique(self):
        if len({r.id for r in self.references}) != len(self.references):
            raise ValueError("Duplicate reference IDs")
        if len({r.box_id for r in self.overrides}) != len(self.overrides):
            raise ValueError("Duplicate box overrides")
        if sum(len(r.text) for r in self.references) > 32768:
            raise ValueError("Reference text exceeds 32768 characters")
        return self
