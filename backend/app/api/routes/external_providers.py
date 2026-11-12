from uuid import uuid4

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.api.dependencies import SessionDep
from app.core.errors import AppError
from app.db.models import ExternalProvider
from app.integrations.external_ocr import ExternalClient
from app.integrations.model_gateway import GatewayError
from app.schemas.dynamic_pipelines import DynamicPipelineInput
from app.schemas.external_providers import ExternalPipelineWrite, ProviderWrite
from app.services.dynamic_pipeline_service import DynamicPipelineService
from app.services.external_provider_service import (
    ExternalProviderService,
    provider_from_record,
    validate_provider,
)
from app.services.serializers import config_json

router = APIRouter()


@router.get("/external-providers")
def providers(request: Request, session: SessionDep):
    service = ExternalProviderService(session, request.app.state.settings)
    return [service.serialize(record) for record in session.scalars(select(ExternalProvider).order_by(ExternalProvider.created_at))]


@router.get("/external-providers/{provider_id}")
def provider(provider_id: str, request: Request, session: SessionDep):
    service = ExternalProviderService(session, request.app.state.settings)
    return service.serialize(service.record(provider_id))


@router.post("/external-providers/validate")
def validate(data: ProviderWrite, request: Request):
    try:
        validate_provider(data, request.app.state.settings)
    except ValueError:
        raise AppError("Provider endpoint configuration is invalid", 422) from None
    return {"status": "configuration_valid", "message": "Configuration syntax valid. Network and inference not tested."}


@router.post("/external-providers", status_code=201)
def create(data: ProviderWrite, request: Request, session: SessionDep):
    service = ExternalProviderService(session, request.app.state.settings)
    return service.serialize(service.save(data))


@router.put("/external-providers/{provider_id}")
def update(provider_id: str, data: ProviderWrite, request: Request, session: SessionDep):
    service = ExternalProviderService(session, request.app.state.settings)
    return service.serialize(service.save(data, provider_id))


@router.delete("/external-providers/{provider_id}", status_code=204)
def remove(provider_id: str, request: Request, session: SessionDep):
    ExternalProviderService(session, request.app.state.settings).delete(provider_id)
    return Response(status_code=204)


@router.post("/external-providers/{provider_id}/test-connection")
async def test_connection(provider_id: str, request: Request, session: SessionDep):
    service = ExternalProviderService(session, request.app.state.settings)
    provider = provider_from_record(service.record(provider_id), request.app.state.settings)
    if not provider._enabled:
        raise AppError("Provider is disabled", 409)
    try:
        return await ExternalClient(request.app.state.settings, provider).request("check_" + uuid4().hex)
    except GatewayError as error:
        return {"status": "unavailable", "message": str(error), "error_code": error.code}


@router.post("/external-pipelines")
def save_pipeline(data: ExternalPipelineWrite, request: Request, session: SessionDep):
    settings = request.app.state.settings
    service = ExternalProviderService(session, settings)
    record = service.save(data.provider, data.provider_id, commit=False)
    provider = provider_from_record(record, settings)
    definition = DynamicPipelineInput(name=data.pipeline_name, enabled=data.pipeline_enabled,
        source="external_api", execution_mode="external_api", provider_id=record.id)
    result = DynamicPipelineService(session, settings).save_pipeline(definition, data.pipeline_id, provider=provider)
    return config_json(result, settings)
