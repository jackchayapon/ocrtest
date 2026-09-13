import json
from uuid import UUID

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from app.api.dependencies import CaseServiceDep, SessionDep
from app.core.errors import AppError
from app.schemas.contracts import AutoROIRequest, BatchRequest
from app.services.auto_roi_service import AutoROIService
from app.services.batch_service import BatchService
from app.services.log_service import LogService
from app.services.serializers import document_json

router = APIRouter(prefix="/documents")


@router.post("/{document_id}/auto-rois")
async def auto_rois(document_id: UUID, data: AutoROIRequest, request: Request, session: SessionDep):
    logs = LogService(session, request.app.state.settings)
    logs.add("auto_roi_requested", document_id=str(document_id), page_number=data.page_number)
    session.commit()
    try:
        async with request.app.state.ocr_lock:
            result = await AutoROIService(
                session, request.app.state.settings, request.app.state.storage
            ).suggest(str(document_id), data)
        logs.add("auto_roi_success", document_id=str(document_id), page_number=data.page_number,
                 gateway_request_id=result.get("request_id"), count=len(result["regions"]))
        session.commit()
        return result
    except Exception:
        session.rollback()
        logs.add("auto_roi_error", document_id=str(document_id), page_number=data.page_number)
        session.commit()
        raise


@router.post("/{document_id}/run-pages")
async def run_pages(document_id: UUID, data: BatchRequest, request: Request, session: SessionDep):
    settings, storage = request.app.state.settings, request.app.state.storage
    BatchService(session, settings, storage).validate(str(document_id), data)

    async def stream():
        async with request.app.state.ocr_lock:
            with request.app.state.database.session_factory() as batch_session:
                service = BatchService(batch_session, settings, storage)
                async for event in service.run(str(document_id), data):
                    yield json.dumps(event, ensure_ascii=False) + "\n"
    return StreamingResponse(stream(), media_type="application/x-ndjson",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"})


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
