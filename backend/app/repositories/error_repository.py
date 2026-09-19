from sqlalchemy import exists, func, select
from sqlalchemy.orm import aliased, noload

from app.db.models import Category, PipelineRun, TestCase
from app.db.models import OCRErrorEvent as Event


class ErrorRepository:
    def __init__(self, session):
        self.session = session

    def aggregate(self, filters, limit, offset):
        # Like Matrix: latest non-archived run per case/pipeline, including failures.
        newer = aliased(PipelineRun)

        def eligible(run):
            return (run.pipeline_id != "hutch_full") | (run.crop_stage == "full_image")

        conditions = [
            ~PipelineRun.archived,
            eligible(PipelineRun),
            Event.error_level == filters.error_level,
            Event.text_kind == filters.text_kind,
            ~exists(
                select(newer.id).where(
                    newer.test_case_id == PipelineRun.test_case_id,
                    newer.pipeline_id == PipelineRun.pipeline_id,
                    ~newer.archived,
                    eligible(newer),
                    (newer.created_at > PipelineRun.created_at)
                    | ((newer.created_at == PipelineRun.created_at) & (newer.id > PipelineRun.id)),
                )
            ),
        ]
        if filters.pipeline:
            conditions.append(PipelineRun.pipeline_id == filters.pipeline)
        if filters.category:
            conditions.append(TestCase.categories.any(Category.code == filters.category))
        if filters.error_type:
            conditions.append(Event.error_type == filters.error_type)
        if filters.test_case_id:
            conditions.append(TestCase.id == str(filters.test_case_id))
        if filters.document:
            conditions.append(TestCase.document_id == str(filters.document))
        columns = (
            PipelineRun.pipeline_id,
            Event.error_type,
            Event.ground_truth_unit,
            Event.ocr_unit,
        )
        base = (
            select(*columns, func.count(Event.id).label("count"))
            .join(PipelineRun, Event.pipeline_run_id == PipelineRun.id)
            .join(TestCase, Event.test_case_id == TestCase.id)
            .where(*conditions)
            .group_by(*columns)
        )
        total = self.session.scalar(select(func.count()).select_from(base.subquery()))
        rows = self.session.execute(
            base.order_by(func.count(Event.id).desc(), *columns).limit(limit).offset(offset)
        )
        items = []
        for pipeline, kind, gt, ocr, count in rows:
            match = [
                PipelineRun.pipeline_id == pipeline,
                Event.error_type == kind,
                Event.ground_truth_unit == gt,
                Event.ocr_unit == ocr,
            ]
            cases_query = (
                select(TestCase)
                .options(noload(TestCase.runs))
                .join(Event, Event.test_case_id == TestCase.id)
                .join(PipelineRun, Event.pipeline_run_id == PipelineRun.id)
                .where(*conditions, *match)
                .distinct()
            )
            case_count = self.session.scalar(
                select(func.count()).select_from(cases_query.subquery())
            )
            cases = list(self.session.scalars(cases_query.order_by(TestCase.id).limit(20)))
            items.append(
                dict(
                    pipeline_id=pipeline,
                    error_type=kind,
                    ground_truth_unit=gt,
                    ocr_unit=ocr,
                    count=count,
                    test_case_count=case_count,
                    cases=[
                        dict(
                            id=c.id,
                            document_id=c.document_id,
                            filename=c.document.filename,
                            page_number=c.page_number,
                            categories=[tag.code for tag in c.categories],
                        )
                        for c in cases
                    ],
                )
            )
        return dict(total=total, items=items, limit=limit, offset=offset)
