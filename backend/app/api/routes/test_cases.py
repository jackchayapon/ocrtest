from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.dependencies import CaseServiceDep, RepoDep, SessionDep
from app.schemas.contracts import (
    BenchmarkFilters,
    BulkCases,
    CategoriesUpdate,
    EvaluationMode,
    FieldCheck,
    GlobalEvaluation,
    GlobalGroundTruth,
    GlobalLayoutUpdate,
    GroundTruthUpdate,
    ROIUpdate,
    RunRequest,
    TestCaseCreate,
    TestCaseUpdate,
)
from app.services.evaluation_insights_service import EvaluationInsightsService
from app.services.field_service import FieldService
from app.services.global_layout_service import GlobalLayoutService
from app.services.serializers import field_json, run_json, test_case_json

router = APIRouter(prefix="/test-cases")


@router.post("/bulk-delete")
async def bulk_delete(data: BulkCases, service: CaseServiceDep, request: Request):
    async with request.app.state.ocr_lock:
        return service.bulk_delete([str(i) for i in data.test_case_ids])


@router.get("/{case_id}/global-fields")
def global_layout(case_id: UUID, repository: RepoDep):
    return test_case_json(repository.test_case(str(case_id)), detail=True)


@router.put("/{case_id}/global-fields")
def save_layout(case_id: UUID, data: GlobalLayoutUpdate, service: CaseServiceDep):
    return test_case_json(GlobalLayoutService(service).layout(str(case_id), data))


@router.put("/{case_id}/global-fields/{field_id}/ground-truth")
def global_gt(case_id: UUID, field_id: UUID, data: GlobalGroundTruth, service: CaseServiceDep):
    return test_case_json(GlobalLayoutService(service).save_gt(str(case_id), str(field_id), data))


@router.put("/{case_id}/evaluation-mode")
def global_mode(case_id: UUID, data: EvaluationMode, service: CaseServiceDep):
    return test_case_json(GlobalLayoutService(service).mode(str(case_id), data.mode))


@router.post("/{case_id}/evaluate")
def evaluate_global(case_id: UUID, data: GlobalEvaluation, service: CaseServiceDep):
    return test_case_json(GlobalLayoutService(service).evaluate(str(case_id), data), detail=True)


@router.post("", status_code=201)
def create_test_case(data: TestCaseCreate, service: CaseServiceDep):
    return test_case_json(service.create(data))


@router.get("")
def list_test_cases(
    repository: RepoDep,
    filters: Annotated[BenchmarkFilters, Depends()],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return [test_case_json(record) for record in repository.cases(filters, limit, offset)]


@router.get("/{case_id}")
def get_test_case(case_id: UUID, repository: RepoDep):
    return test_case_json(repository.test_case(str(case_id)), detail=True)


@router.put("/{case_id}")
def update_test_case(case_id: UUID, data: TestCaseUpdate, service: CaseServiceDep):
    return test_case_json(service.update(str(case_id), data))


@router.put("/{case_id}/ground-truth")
def save_ground_truth(case_id: UUID, data: GroundTruthUpdate, service: CaseServiceDep):
    return test_case_json(service.ground_truth(str(case_id), data))


@router.put("/{case_id}/roi")
def update_roi(case_id: UUID, data: ROIUpdate, service: CaseServiceDep):
    return test_case_json(service.update(str(case_id), TestCaseUpdate(roi=data.roi, roi_source=data.roi_source)))


@router.get("/{case_id}/runs/{run_id}/fields")
def fields(case_id: UUID, run_id: UUID, session: SessionDep):
    return [field_json(field, detail=True) for field in FieldService(session).list_fields(str(case_id), str(run_id))]


@router.post("/{case_id}/runs/{run_id}/fields/{field_id}/check")
def check_field(case_id: UUID, run_id: UUID, field_id: UUID, data: FieldCheck, session: SessionDep):
    return FieldService(session).check(str(case_id), str(run_id), str(field_id), data.ground_truth_raw)


@router.put("/{case_id}/runs/{run_id}/fields/{field_id}/ground-truth")
def field_ground_truth(case_id: UUID, run_id: UUID, field_id: UUID, data: GroundTruthUpdate, session: SessionDep):
    return field_json(FieldService(session).update(str(case_id), str(run_id), str(field_id), data), detail=True)


@router.put("/{case_id}/categories")
def update_categories(case_id: UUID, data: CategoriesUpdate, service: CaseServiceDep):
    return test_case_json(
        service.update(str(case_id), TestCaseUpdate(category_codes=data.category_codes))
    )


@router.post("/{case_id}/run")
async def run_test_case(case_id: UUID, data: RunRequest, service: CaseServiceDep, request: Request):
    async with request.app.state.ocr_lock:
        return {
            "test_case_id": str(case_id),
            "runs": [run_json(run) for run in await service.run(str(case_id), data.pipelines)],
        }


@router.delete("/{case_id}", status_code=204)
async def delete_test_case(case_id: UUID, service: CaseServiceDep, request: Request):
    async with request.app.state.ocr_lock:
        service.delete(str(case_id))
    return Response(status_code=204)


@router.get("/{case_id}/results")
def get_results(case_id: UUID, repository: RepoDep):
    return {
        "test_case_id": str(case_id),
        "runs": [run_json(run, detail=True) for run in repository.test_case(str(case_id)).runs if not run.archived],
    }


@router.get("/{case_id}/error-summary")
def error_summary(case_id: UUID, session: SessionDep,
                  pipeline_id: str = Query(min_length=1, max_length=50),
                  field_id: UUID | None = None,
                  mode: Literal["per_field", "whole_document"] | None = None,
                  character: str | None = Query(default=None, min_length=1, max_length=1)):
    return EvaluationInsightsService(session).report(str(case_id), pipeline_id,
        str(field_id) if field_id else None, mode, character)


@router.get("/{case_id}/evaluation-report")
def evaluation_report(case_id: UUID, session: SessionDep,
                      mode: Literal["per_field", "whole_document"] | None = None):
    payload = EvaluationInsightsService(session).export(str(case_id), mode)
    return Response(payload, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="evaluation-{case_id}.zip"',
        "Cache-Control": "private, no-store",
    })
