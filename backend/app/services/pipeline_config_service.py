from app.core.errors import AppError
from app.integrations.model_gateway import ModelGatewayClient
from app.repositories.benchmark_repository import BenchmarkRepository


class PipelineConfigService:
    def __init__(self, session, settings):
        self.repository = BenchmarkRepository(session)
        self.settings = settings

    def update(self, pipeline_id, data):
        config = self.repository.config(pipeline_id)
        expected_engine = "custom" if pipeline_id == "mint" else "paddle"
        values = data.model_dump(exclude_unset=True)
        if (
            values.get("engine") not in (None, expected_engine)
            or values.get("query_params", {}).get("engine", expected_engine) != expected_engine
        ):
            raise AppError("The pipeline engine is fixed by the benchmark definition", 422)
        for key, value in values.items():
            setattr(config, key, value)
        config.engine = expected_engine
        config.query_params = {"engine": expected_engine}
        config.include_roi = False
        config.file_field_name = "image"
        config.last_connection_status = None
        return self.repository.save(config)

    async def test_connection(self, pipeline_id):
        config = self.repository.config(pipeline_id)
        if not self.settings.api_key(pipeline_id):
            status, message = "missing_key", "ยังไม่ได้ตั้งค่า API Key"
        elif not self.settings.model_gateway_base_url or not config.endpoint:
            status, message = (
                "not_configured",
                "กรุณาตั้งค่า Gateway URL และ endpoint",
            )
        else:
            result = await ModelGatewayClient(self.settings).status()
            status = result[pipeline_id]
            message = f"Gateway: {result['gateway']}. Pipeline: {status}. " + result.get(
                "message", ""
            )
        config.last_connection_status = status
        self.repository.save(config)
        return {"status": status, "message": message}
