from fastapi import APIRouter, Request

from app.api.dependencies import RepoDep, SessionDep
from app.schemas.contracts import PipelineConfigUpdate
from app.services.pipeline_config_service import PipelineConfigService
from app.services.serializers import config_json

router = APIRouter(prefix="/pipelines")


@router.get("")
def pipelines(request: Request, repository: RepoDep):
    return [config_json(config, request.app.state.settings) for config in repository.configs()]


@router.get("/{pipeline_id}")
def get_pipeline(pipeline_id: str, request: Request, repository: RepoDep):
    return config_json(repository.config(pipeline_id), request.app.state.settings)


@router.put("/{pipeline_id}")
def update_pipeline(
    pipeline_id: str, data: PipelineConfigUpdate, request: Request, session: SessionDep
):
    return config_json(
        PipelineConfigService(session, request.app.state.settings).update(pipeline_id, data),
        request.app.state.settings,
    )


@router.post("/{pipeline_id}/test-connection")
async def test_connection(pipeline_id: str, request: Request, session: SessionDep):
    return await PipelineConfigService(session, request.app.state.settings).test_connection(
        pipeline_id
    )
