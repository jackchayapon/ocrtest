"""Case-first projections; no ORM relationship loading or vendor JSON."""

from sqlalchemy import func, literal, select

from app.core.errors import AppError
from app.db.models import Document, GlobalField, OCRField, PipelineRun, TestCase


class EvaluationInsightsRepository:
    def __init__(self, session):
        self.session = session

    def read(self, case_id, pipeline_id=None, field_id=None, *, selection=None):
        case_query = (
            select(
                TestCase.id,
                TestCase.document_id,
                TestCase.page_number,
                TestCase.workflow,
                TestCase.evaluation_mode,
                TestCase.updated_at,
                literal(None).label("ground_truth_raw") if field_id else TestCase.ground_truth_raw,
                TestCase.document_gt_confirmed_at,
                TestCase.status,
                TestCase.roi,
                Document.filename,
                Document.width,
                Document.height,
                TestCase.page_width,
                TestCase.page_height,
            )
            .join(Document, Document.id == TestCase.document_id)
            .where(TestCase.id == case_id)
        )
        if selection:
            case_query = case_query.with_for_update(read=True)
        case = self.session.execute(case_query).mappings().first()
        if case is None:
            raise AppError("Test case not found", 404)
        candidates = select(
            PipelineRun.id,
            func.row_number()
            .over(
                partition_by=PipelineRun.pipeline_id,
                order_by=(PipelineRun.created_at.desc(), PipelineRun.id.desc()),
            )
            .label("rank"),
        ).where(PipelineRun.test_case_id == case_id, PipelineRun.archived.is_(False))
        if pipeline_id:
            candidates = candidates.where(PipelineRun.pipeline_id == pipeline_id)
        if selection:
            candidates = candidates.where(PipelineRun.pipeline_id.in_(selection.pipeline_ids))
        ranked = candidates.subquery()
        runs = (
            self.session.execute(
                select(
                    PipelineRun.id,
                    PipelineRun.pipeline_id,
                    PipelineRun.pipeline_name,
                    PipelineRun.status,
                    literal(None).label("final_text") if field_id else PipelineRun.final_text,
                    PipelineRun.confidence,
                    PipelineRun.processing_time_ms,
                    literal(None).label("document_evaluation")
                    if field_id
                    else PipelineRun.document_evaluation,
                    PipelineRun.roi,
                )
                .join(ranked, ranked.c.id == PipelineRun.id)
                .where(ranked.c.rank == 1)
                .order_by(PipelineRun.pipeline_id)
                .limit(101)
            )
            .mappings()
            .all()
        )
        if pipeline_id and not runs:
            raise AppError("Pipeline has no eligible run in this case", 404)
        if len(runs) > 100:
            raise AppError("Report limited to 100 pipelines", 413)
        globals_query = select(
            GlobalField.id,
            GlobalField.field_index,
            GlobalField.roi,
            GlobalField.ground_truth_raw,
            GlobalField.confirmed_at,
        ).where(GlobalField.test_case_id == case_id)
        if field_id:
            globals_query = globals_query.where(GlobalField.id == field_id)
        if selection and selection.mode == "per_field":
            globals_query = globals_query.where(
                GlobalField.id.in_([str(i) for i in selection.field_ids])
            )
        globals_ = (
            self.session.execute(globals_query.order_by(GlobalField.field_index)).mappings().all()
        )
        query = select(
            OCRField.id,
            OCRField.pipeline_run_id,
            OCRField.global_field_id,
            OCRField.field_index,
            OCRField.ocr_text,
            OCRField.ground_truth_raw,
            OCRField.confirmed_at,
            OCRField.evaluation,
            OCRField.status,
            OCRField.confidence,
        ).where(OCRField.pipeline_run_id.in_([r["id"] for r in runs]))
        if field_id:
            query = query.where((OCRField.global_field_id == field_id) | (OCRField.id == field_id))
        if selection and selection.mode == "per_field":
            query = query.where(OCRField.global_field_id.in_([str(i) for i in selection.field_ids]))
        fields = (
            self.session.execute(query.order_by(OCRField.field_index).limit(2001)).mappings().all()
        )
        if len(fields) > 2000:
            raise AppError("Report limited to 2,000 fields; select a pipeline", 413)
        if field_id and not globals_ and not fields:
            raise AppError("Field does not belong to the selected case/pipeline", 404)
        return (
            dict(case),
            [dict(r) for r in runs],
            [dict(f) for f in globals_],
            [dict(f) for f in fields],
        )
