from datetime import datetime, time, timedelta, timezone

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session, aliased, load_only, raiseload, selectinload

from app.core.errors import AppError
from app.db.models import (
    Category,
    Document,
    GlobalField,
    Metric,
    OCRField,
    PipelineConfig,
    PipelineRun,
    TestCase,
)
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

    def test_case(self, case_id: str, *, for_update=False) -> TestCase:
        record = self.session.get(TestCase, case_id, with_for_update=for_update)
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

    def configs(self, *, summary=False) -> list[PipelineConfig]:
        query = select(PipelineConfig).where(PipelineConfig.execution_mode.is_not(None))
        if summary:
            query = query.options(load_only(PipelineConfig.pipeline_id, PipelineConfig.name,
                                           PipelineConfig.enabled, raiseload=True), raiseload("*"))
        return list(self.session.scalars(query.order_by(PipelineConfig.created_at, PipelineConfig.pipeline_id)))

    def config(self, pipeline_id: str) -> PipelineConfig:
        record = self.session.scalar(
            select(PipelineConfig).where(PipelineConfig.pipeline_id == pipeline_id, PipelineConfig.execution_mode.is_not(None))
        )
        if record is None:
            raise AppError("Pipeline not found", 404)
        return record

    def cases(
        self, filters: BenchmarkFilters, limit: int | None = None, offset: int = 0, *, runs_only=False,
        analytics=False, summary=False, texts=False, test_case_id=None, latest=False,
    ) -> list[TestCase]:
        query = select(TestCase)
        if summary:
            visible_runs = PipelineRun.archived.is_(False)
            if latest:
                newer = aliased(PipelineRun)
                # The selectin query limits case IDs first. Compare only another
                # non-archived run for this same case/pipeline; keep full history elsewhere.
                newer_run = exists(select(newer.id).where(
                    newer.test_case_id == PipelineRun.test_case_id,
                    newer.pipeline_id == PipelineRun.pipeline_id,
                    newer.archived.is_(False),
                    or_(newer.created_at > PipelineRun.created_at,
                        and_(newer.created_at == PipelineRun.created_at, newer.id > PipelineRun.id)),
                ))
                visible_runs = and_(visible_runs, ~newer_run)
            query = query.options(
                selectinload(TestCase.runs.and_(visible_runs))
                    .defer(PipelineRun.raw_response, raiseload=True).defer(PipelineRun.boxes, raiseload=True),
                selectinload(TestCase.runs.and_(visible_runs))
                    .selectinload(PipelineRun.fields).defer(OCRField.diagnostics, raiseload=True),
            )
        if analytics:
            run_columns = [PipelineRun.test_case_id, PipelineRun.pipeline_id, PipelineRun.pipeline_name,
                PipelineRun.status, PipelineRun.archived, PipelineRun.crop_stage, PipelineRun.created_at,
                PipelineRun.confidence, PipelineRun.processing_time_ms, PipelineRun.gateway_duration_ms,
                PipelineRun.document_evaluation]
            field_columns = [OCRField.pipeline_run_id, OCRField.global_field_id, OCRField.status,
                OCRField.confirmed_at, OCRField.evaluation, OCRField.ground_truth_raw]
            if texts:
                run_columns += [PipelineRun.raw_text, PipelineRun.final_text]
                field_columns += [OCRField.ocr_text]
            query = query.options(
                load_only(TestCase.document_id, TestCase.page_number, TestCase.workflow,
                          TestCase.evaluation_mode, TestCase.document_gt_confirmed_at,
                          TestCase.ground_truth_raw, TestCase.status, raiseload=True),
                selectinload(TestCase.document).load_only(Document.filename, Document.document_type_id,
                                                        raiseload=True).raiseload(Document.business_type),
                selectinload(TestCase.global_fields).load_only(GlobalField.ground_truth_raw,
                    GlobalField.confirmed_at, raiseload=True),
                selectinload(TestCase.runs).load_only(*run_columns, raiseload=True),
                selectinload(TestCase.runs).selectinload(PipelineRun.fields).load_only(*field_columns, raiseload=True),
                selectinload(TestCase.runs).selectinload(PipelineRun.metric_records).load_only(
                    Metric.text_kind, Metric.cer, Metric.wer, Metric.exact_match, Metric.created_at, raiseload=True),
            )
        if test_case_id is not None:
            query = query.where(TestCase.id == str(test_case_id))
        if runs_only:
            query = query.where(TestCase.runs.any())
        if filters.category:
            query = query.where(TestCase.categories.any(Category.code == filters.category))
        if filters.document_type_id:
            query = query.where(TestCase.document.has(Document.document_type_id == str(filters.document_type_id)))
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
