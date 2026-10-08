from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.dependencies import SessionDep
from app.core.errors import AppError
from app.db.models import DocumentType
from app.services.config_cache import catalog
from app.services.document_type_service import create_type, type_json

router = APIRouter(prefix="/document-types")


class CreateType(BaseModel):
    name: str = Field(max_length=200)


@router.get("")
def list_types(request: Request, fresh: bool = False):
    return catalog(request, "document-types", lambda s: [type_json(r) for r in s.scalars(
        select(DocumentType).where(DocumentType.active.is_(True)).order_by(DocumentType.system.desc(), DocumentType.name)
    )], fresh=fresh)


@router.post("", status_code=201)
def add_type(data: CreateType, session: SessionDep):
    return type_json(create_type(session, data.name))


@router.delete("/{id}")
def archive_type(id: UUID, session: SessionDep):
    record = session.get(DocumentType, str(id))
    if record is None:
        raise AppError("ไม่พบประเภทเอกสาร", 404)
    if record.system:
        raise AppError("ไม่สามารถลบประเภทเอกสารของระบบ", 409)
    record.active = False
    session.commit()
    return type_json(record)
