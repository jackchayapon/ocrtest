from sqlalchemy import JSON, func, select
from sqlalchemy.orm import noload

from app.core.errors import AppError
from app.db.models import Category, TestCase


class DatasetRepository:
    def __init__(self, session):
        self.session = session

    @staticmethod
    def eligible(case):
        return case.status == "confirmed" and case.ground_truth_raw is not None and bool(case.roi)

    def samples(self, category, document, limit, offset):
        query = (
            select(TestCase)
            .options(noload(TestCase.runs))
            .where(
                TestCase.status == "confirmed",
                TestCase.ground_truth_raw.is_not(None),
                TestCase.roi.is_not(None),
                TestCase.roi != JSON.NULL,
            )
        )
        if category:
            query = query.where(TestCase.categories.any(Category.code == category))
        if document:
            query = query.where(TestCase.document_id == str(document))
        total = self.session.scalar(select(func.count()).select_from(query.subquery()))
        return total, list(
            self.session.scalars(query.order_by(TestCase.id).limit(limit).offset(offset))
        )

    def selected(self, ids):
        cases = list(
            self.session.scalars(
                select(TestCase)
                .options(noload(TestCase.runs))
                .where(TestCase.id.in_(ids))
                .order_by(TestCase.id)
            )
        )
        if len(cases) != len(ids):
            raise AppError("One or more selected test cases no longer exist", 404)
        if any(not self.eligible(case) for case in cases):
            raise AppError("Dataset samples require a saved ROI and confirmed Ground Truth", 422)
        return cases
