from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Category, Document, PipelineConfig, PipelineRun, TestCase
from app.schemas.contracts import BenchmarkFilters


class BenchmarkRepository:
    """Database access stays here; routes and adapters do not build database queries."""

    def __init__(self, session: Session):
        self.session = session

    def document(self, document_id: str) -> Document:
        record = self.session.get(Document, document_id)
        if record is None:
            raise AppError("Document not found", 404)
        return record

    def test_case(self, case_id: str) -> TestCase:
        record = self.session.get(TestCase, case_id)
        if record is None:
            raise AppError("Test case not found", 404)
        return record

    def categories(self, codes=None) -> list[Category]:
        query = select(Category).order_by(Category.display_name)
        if codes is not None:
            query = query.where(Category.code.in_(set(codes)))
        results = list(self.session.scalars(query))
        if codes is not None and len(results) != len(set(codes)):
            raise AppError("One or more categories are unknown", 422)
        return results

    def configs(self) -> list[PipelineConfig]:
        return sorted(
            self.session.scalars(select(PipelineConfig)),
            key=lambda row: ("mint", "hutch_crop", "hutch_full").index(row.pipeline_id),
        )

    def config(self, pipeline_id: str) -> PipelineConfig:
        record = self.session.scalar(
            select(PipelineConfig).where(PipelineConfig.pipeline_id == pipeline_id)
        )
        if record is None:
            raise AppError("Pipeline not found", 404)
        return record

    def cases(
        self, filters: BenchmarkFilters, limit: int | None = None, offset: int = 0
    ) -> list[TestCase]:
        query = select(TestCase)
        if filters.category:
            query = query.where(TestCase.categories.any(Category.code == filters.category))
        if filters.pipeline:
            query = query.where(TestCase.runs.any(PipelineRun.pipeline_id == filters.pipeline))
        if filters.document:
            query = query.where(TestCase.document_id == str(filters.document))
        if filters.date_from:
            query = query.where(
                TestCase.created_at >= datetime.combine(filters.date_from, time.min, timezone.utc)
            )
        if filters.date_to:
            query = query.where(
                TestCase.created_at
                < datetime.combine(filters.date_to + timedelta(days=1), time.min, timezone.utc)
            )
        query = query.order_by(TestCase.created_at.desc(), TestCase.id).offset(offset)
        if limit is not None:
            query = query.limit(limit)
        return list(self.session.scalars(query))

    def save(self, record):
        self.session.add(record)
        self.session.commit()
        return record
