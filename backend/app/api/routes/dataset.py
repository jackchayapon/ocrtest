from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.api.dependencies import CaseServiceDep
from app.schemas.contracts import DatasetExport
from app.services.dataset_service import DatasetService

router = APIRouter(prefix="/dataset")


@router.get("/samples")
def samples(
    service: CaseServiceDep,
    category: str | None = None,
    document: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return DatasetService(service).samples(category, document, limit, offset)


@router.post("/export")
def export(data: DatasetExport, service: CaseServiceDep):
    output = DatasetService(service).export([str(id) for id in data.test_case_ids])

    def chunks():
        try:
            while chunk := output.read(64 * 1024):
                yield chunk
        finally:
            output.close()

    return StreamingResponse(
        chunks(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="dataset.zip"'},
        background=BackgroundTask(output.close),
    )
