from app.repositories.benchmark_repository import BenchmarkRepository
from app.repositories.error_repository import ErrorRepository
from app.services.test_case_service import TestCaseService


class ErrorAnalysisService:
    def __init__(self, session):
        self.repository = BenchmarkRepository(session)
        self.errors = ErrorRepository(session)

    def aggregate(self, filters, limit, offset):
        return self.errors.aggregate(filters, limit, offset)

    def recompute(self, case_id):
        # Explicit, per-case backfill. No upstream OCR or destructive bulk migration.
        record = self.repository.test_case(case_id, for_update=True)
        count = 0
        for run in record.runs:
            if not run.archived:
                TestCaseService.evaluate(run, record.ground_truth_raw)
                count += 1
        self.repository.save(record)
        return {"test_case_id": record.id, "recomputed_runs": count}
