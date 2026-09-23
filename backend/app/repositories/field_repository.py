from sqlalchemy import select

from app.core.errors import AppError
from app.db.models import OCRField, PipelineRun


class FieldRepository:
    def __init__(self, session):
        self.session = session

    def run(self, case_id, run_id, *, lock=False):
        query = select(PipelineRun).where(
            PipelineRun.id == run_id,
            PipelineRun.test_case_id == case_id,
            PipelineRun.archived.is_(False),
        )
        if lock:
            query = query.with_for_update()
        run = self.session.scalar(query)
        if run is None:
            raise AppError("Pipeline run not found", 404)
        return run

    def field(self, case_id, run_id, field_id, *, lock=False):
        self.run(case_id, run_id, lock=lock)
        field = self.session.scalar(
            select(OCRField).where(OCRField.id == field_id, OCRField.pipeline_run_id == run_id)
        )
        if field is None:
            raise AppError("OCR field not found", 404)
        return field

    def save(self):
        self.session.commit()
