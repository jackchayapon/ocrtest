from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import RepoDep, SessionDep
from app.schemas.contracts import BenchmarkFilters, ErrorFilters
from app.services.error_analysis_service import ErrorAnalysisService
from app.services.matrix_service import MatrixService
from app.services.serializers import category_json, test_case_json

router = APIRouter()


@router.get("/history")
def history(
    repository: RepoDep,
    filters: Annotated[BenchmarkFilters, Depends()],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return [test_case_json(record) for record in repository.cases(filters, limit, offset)]


@router.get("/categories")
def categories(repository: RepoDep):
    return [category_json(record) for record in repository.categories()]


@router.get("/matrix")
def matrix(session: SessionDep, filters: Annotated[BenchmarkFilters, Depends()]):
    return MatrixService(session).matrix(filters)


@router.get("/analytics/categories")
def category_analytics(session: SessionDep, filters: Annotated[BenchmarkFilters, Depends()]):
    return MatrixService(session).categories(filters)


@router.get("/analytics/errors")
def error_analytics(session: SessionDep, filters: Annotated[ErrorFilters, Depends()],
                    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    return ErrorAnalysisService(session).aggregate(filters, limit, offset)


@router.post("/test-cases/{case_id}/errors/recompute")
def recompute_errors(case_id: UUID, session: SessionDep):
    return ErrorAnalysisService(session).recompute(str(case_id))
