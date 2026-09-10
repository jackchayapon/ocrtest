from uuid import UUID

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import Response

from app.api.dependencies import CaseServiceDep, SessionDep
from app.core.errors import AppError
from app.schemas.contracts import AutoROIRequest
from app.services.auto_roi_service import AutoROIService
from app.services.serializers import document_json

router = APIRouter(prefix="/documents")


@router.post("/{document_id}/auto-rois")
async def auto_rois(document_id: UUID, data: AutoROIRequest, request: Request, session: SessionDep):
    return await AutoROIService(
        session, request.app.state.settings, request.app.state.storage
    ).suggest(str(document_id), data)


@router.post("", status_code=201)
async def upload_document(request: Request, service: CaseServiceDep, file: UploadFile = File(...)):
    try:
        data = await file.read(request.app.state.settings.max_upload_mb * 1024 * 1024 + 1)
        return document_json(
            service.upload(data, file.filename or "document.png", file.content_type or "")
        )
    finally:
        await file.close()


@router.get("/{document_id}")
def get_document(
    document_id: UUID, service: CaseServiceDep, page_number: int | None = Query(default=None, ge=1)
):
    return service.page_metadata(str(document_id), page_number)


@router.get("/{document_id}/pages/{page_number}/image")
def page_image(document_id: UUID, page_number: int, service: CaseServiceDep):
    return Response(
        service.image_bytes(str(document_id), page_number=page_number),
        media_type="image/png",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/{document_id}/image")
def document_image(document_id: UUID, service: CaseServiceDep):
    return Response(
        service.image_bytes(str(document_id)),
        media_type="image/png",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/{document_id}/crop")
def crop_image(
    document_id: UUID,
    service: CaseServiceDep,
    x1: int = Query(ge=0),
    y1: int = Query(ge=0),
    x2: int = Query(gt=0),
    y2: int = Query(gt=0),
    page_number: int | None = Query(default=None, ge=1),
):
    if x2 <= x1 or y2 <= y1:
        raise AppError("ROI must have positive dimensions", 422)
    return Response(
        service.image_bytes(
            str(document_id), {"x1": x1, "y1": y1, "x2": x2, "y2": y2}, page_number
        ),
        media_type="image/png",
        headers={"Cache-Control": "private, no-store"},
    )
