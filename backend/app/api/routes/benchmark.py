from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import RepoDep, SessionDep
from app.repositories.benchmark_repository import BenchmarkRepository
from app.schemas.contracts import BenchmarkFilters, ErrorFilters
from app.services.config_cache import catalog
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
    view: Literal["full", "summary"] = "full",
    latest: bool = False,
):
    return [test_case_json(record, summary=view == "summary") for record in
            repository.cases(filters, limit, offset, runs_only=True, summary=view == "summary", latest=latest and view == "summary")]


@router.get("/categories")
def categories(request: Request, fresh: bool = False):
    return catalog(request, "categories", lambda s: [category_json(r) for r in BenchmarkRepository(s).categories()], fresh=fresh)


@router.get("/matrix")
def matrix(session: SessionDep, filters: Annotated[BenchmarkFilters, Depends()]):
    return MatrixService(session).matrix(filters)


@router.get("/analytics/categories")
def category_analytics(session: SessionDep, filters: Annotated[BenchmarkFilters, Depends()]):
    return MatrixService(session).categories(filters)


@router.get("/analytics/summary")
def analytics_summary(session: SessionDep, filters: Annotated[BenchmarkFilters, Depends()],
                      dashboard: bool = False, include_archived: bool = False):
    service = MatrixService(session)
    return service.dashboard(filters, include_archived) if dashboard else service.summary(filters)


@router.get("/analytics/pipelines")
def analytics_pipelines(session: SessionDep):
    return MatrixService(session).options()


@router.get("/analytics/comparison")
def comparison_decision(session: SessionDep, filters: Annotated[BenchmarkFilters, Depends()],
                        include_archived: bool = False):
    return MatrixService(session).decision(filters, include_archived)


@router.get("/analytics/document-types")
def document_type_analytics(session: SessionDep, filters: Annotated[BenchmarkFilters, Depends()]):
    return MatrixService(session).groups(filters, "document_type")


@router.get("/analytics/errors")
def error_analytics(session: SessionDep, filters: Annotated[ErrorFilters, Depends()],
                    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    return ErrorAnalysisService(session).aggregate(filters, limit, offset)


@router.post("/test-cases/{case_id}/errors/recompute")
def recompute_errors(case_id: UUID, session: SessionDep):
    return ErrorAnalysisService(session).recompute(str(case_id))
