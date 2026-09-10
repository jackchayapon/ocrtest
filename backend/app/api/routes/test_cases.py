from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import CaseServiceDep, RepoDep
from app.schemas.contracts import (
    BenchmarkFilters,
    CategoriesUpdate,
    GroundTruthUpdate,
    ROIUpdate,
    RunRequest,
    TestCaseCreate,
    TestCaseUpdate,
)
from app.services.serializers import run_json, test_case_json

router = APIRouter(prefix="/test-cases")


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
    return test_case_json(repository.test_case(str(case_id)))


@router.put("/{case_id}")
def update_test_case(case_id: UUID, data: TestCaseUpdate, service: CaseServiceDep):
    return test_case_json(service.update(str(case_id), data))


@router.put("/{case_id}/ground-truth")
def save_ground_truth(case_id: UUID, data: GroundTruthUpdate, service: CaseServiceDep):
    return test_case_json(service.ground_truth(str(case_id), data))


@router.put("/{case_id}/roi")
def update_roi(case_id: UUID, data: ROIUpdate, service: CaseServiceDep):
    return test_case_json(service.update(str(case_id), TestCaseUpdate(roi=data.roi)))


@router.put("/{case_id}/categories")
def update_categories(case_id: UUID, data: CategoriesUpdate, service: CaseServiceDep):
    return test_case_json(
        service.update(str(case_id), TestCaseUpdate(category_codes=data.category_codes))
    )


@router.post("/{case_id}/run")
async def run_test_case(case_id: UUID, data: RunRequest, service: CaseServiceDep):
    return {
        "test_case_id": str(case_id),
        "runs": [run_json(run) for run in await service.run(str(case_id), data.pipelines)],
    }


@router.get("/{case_id}/results")
def get_results(case_id: UUID, repository: RepoDep):
    return {
        "test_case_id": str(case_id),
        "runs": [run_json(run) for run in repository.test_case(str(case_id)).runs if not run.archived],
    }
