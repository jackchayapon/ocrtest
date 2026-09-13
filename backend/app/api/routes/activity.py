from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.dependencies import SessionDep
from app.db.models import AppLog

router = APIRouter(prefix="/logs")


@router.get("")
def logs(session: SessionDep, level: Literal["INFO", "WARNING", "ERROR"] | None = None,
         event_type: str | None = Query(default=None, max_length=50),
         pipeline: str | None = Query(default=None, max_length=50),
         request_id: str | None = Query(default=None, max_length=100),
         test_case_id: UUID | None = None, date_from: datetime | None = None,
         date_to: datetime | None = None, limit: int = Query(default=25, ge=1, le=100),
         offset: int = Query(default=0, ge=0)):
    query = select(AppLog)
    for column, value in ((AppLog.level, level), (AppLog.event_type, event_type),
                          (AppLog.pipeline_id, pipeline),
                          (AppLog.test_case_id, str(test_case_id) if test_case_id else None)):
        if value is not None:
            query = query.where(column == value)
    if request_id:
        query = query.where(AppLog.request_id.contains(request_id, autoescape=True))
    if date_from:
        query = query.where(AppLog.created_at >= date_from)
    if date_to:
        query = query.where(AppLog.created_at <= date_to)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    records = session.scalars(query.order_by(AppLog.created_at.desc(), AppLog.id.desc()).limit(limit).offset(offset))
    return {"total": total, "items": [{
        "id": row.id, "created_at": row.created_at.isoformat(), "level": row.level,
        "event_type": row.event_type, "message": row.message, "test_case_id": row.test_case_id,
        "document_id": row.document_id, "page_number": row.page_number,
        "pipeline_id": row.pipeline_id, "request_id": row.request_id,
        "gateway_request_id": row.gateway_request_id, "metadata": row.details,
    } for row in records]}
