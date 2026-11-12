from app.core.errors import AppError
from app.integrations.model_gateway import ModelGatewayClient
from app.repositories.benchmark_repository import BenchmarkRepository
from app.services.pipeline_manager import PipelineManager


class PipelineConfigService:
    def __init__(self, session, settings):
        self.repository = BenchmarkRepository(session)
        self.settings = settings

    def update(self, pipeline_id, data):
        config = self.repository.config(pipeline_id)
        # Current catalog definitions have no built-in adapter_classes registry.
        # Keep this compatibility route limited to presentation/availability;
        # model and routing edits use the validated /definition endpoint.
        if config.execution_mode:
            values = data.model_dump(exclude_unset=True)
            if set(values) - {"name", "enabled"}:
                raise AppError("Edit model and routing options through the pipeline definition", 422)
            for key, value in values.items():
                setattr(config, key, value)
            config.last_connection_status = None
            return self.repository.save(config)
        adapter = PipelineManager.adapter_classes.get(pipeline_id)
        if adapter is None:
            raise AppError("Register an adapter with a verified API contract before configuring this pipeline", 422)
        expected_engine = adapter.engine
        values = data.model_dump(exclude_unset=True)
        if pipeline_id == "hutch_fine_tune_v2":
            fixed = dict(endpoint="/api/v1/text-recognition-batches", engine=expected_engine,
                         query_params={"version": "5", "model": "thai_ft_v2"},
                         request_format="multipart", file_field_name="images")
            if any(key in values and values[key] != value for key, value in fixed.items()):
                raise AppError("Hutch fine tune v2 uses REC V5 with model=thai_ft_v2 only", 422)
            for key, value in {**values, **fixed}.items():
                setattr(config, key, value)
            config.include_roi = False
            config.last_connection_status = None
            return self.repository.save(config)
        if pipeline_id in {"benchmark", "thai_ft_v2"}:
            query = {"version": "6"}
            if pipeline_id == "thai_ft_v2":
                query["model"] = "thai_ft_v2"
            fixed = dict(endpoint="/api/v1/text-detection-batches", engine=expected_engine,
                         query_params=query, request_format="multipart", file_field_name="images")
            if any(key in values and values[key] != value for key, value in fixed.items()):
                raise AppError(
                    "Thai FT v2 uses fixed DET V6 / REC V6 with model=thai_ft_v2"
                    if pipeline_id == "thai_ft_v2" else
                    "Benchmark uses fixed DET V6 / REC V5 batch endpoints without a model parameter", 422)
            for key, value in {**values, **fixed}.items():
                setattr(config, key, value)
            config.include_roi = False
            config.last_connection_status = None
            return self.repository.save(config)
        if set(values.get("query_params", {})) - {"engine"} or values.get("file_field_name", "image") != "image":
            raise AppError("This pipeline uses the image field and engine query parameter", 422)
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
        if config.execution_mode == "external_api":
            from uuid import uuid4

            from app.integrations.external_ocr import ExternalClient, get_provider
            from app.integrations.model_gateway import GatewayError
            provider = get_provider(self.settings, (config.integrated_options or {}).get("provider_id"))
            try:
                result = await ExternalClient(self.settings, provider).request("check_" + uuid4().hex)
            except GatewayError as error:
                result = {"status": "unavailable", "message": str(error), "error_code": error.code}
            config.last_connection_status = result["status"]
            self.repository.save(config)
            return result
        if config.execution_mode:
            if not self.settings.api_key(pipeline_id):
                config.last_connection_status = "missing_key"
                self.repository.save(config)
                return {"status": "missing_key", "message": "Configure MODEL_GATEWAY_API_KEY first"}
            result = await ModelGatewayClient(self.settings).status()
            status = "gateway_connected" if result["gateway"] == "connected" else "unavailable"
            # Official dynamic selections still call integrated Paddle, even det_rec/rec mode.
            service_key = "hutch_crop" if config.source == "official" else "mint" if config.execution_mode == "integrated" else None
            if service_key and result.get(service_key) == "unavailable":
                status = "unavailable"
            if config.source == "custom" and config.execution_mode in {"det_rec", "rec"}:
                needed = ("det", "rec") if config.execution_mode == "det_rec" else ("rec",)
                if any(result.get("services", {}).get(name) == "unavailable" for name in needed):
                    status = "unavailable"
            if "not_authenticated" in result.values():
                status = "not_authenticated"
            config.last_connection_status = status
            self.repository.save(config)
            message = ("เชื่อมต่อ Gateway สำเร็จ — ทดสอบ OCR เพื่อยืนยันโมเดลที่เลือก"
                       if status == "gateway_connected" else
                       "เชื่อมต่อ Gateway ได้ แต่บริการที่ Pipeline นี้ต้องใช้ยังไม่พร้อมใช้งาน"
                       if result["gateway"] == "connected" and status == "unavailable" else
                       "เชื่อมต่อ Gateway ไม่สำเร็จ กรุณาตรวจการเชื่อมต่อและ API Key")
            return {"status": status, "message": message}
        if pipeline_id not in PipelineManager.adapter_classes:
            return {"status": "not_configured", "message": "No adapter is registered for this pipeline"}
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
