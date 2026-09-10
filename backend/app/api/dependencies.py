from typing import Annotated

from fastapi import Depends, Request

from app.repositories.benchmark_repository import BenchmarkRepository
from app.services.test_case_service import TestCaseService


def session_dependency(request: Request):
    with request.app.state.database.session_factory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise


SessionDep = Annotated[object, Depends(session_dependency)]


def repository_dependency(session: SessionDep):
    return BenchmarkRepository(session)


def case_service_dependency(request: Request, session: SessionDep):
    return TestCaseService(session, request.app.state.settings, request.app.state.storage)


RepoDep = Annotated[BenchmarkRepository, Depends(repository_dependency)]
CaseServiceDep = Annotated[TestCaseService, Depends(case_service_dependency)]
