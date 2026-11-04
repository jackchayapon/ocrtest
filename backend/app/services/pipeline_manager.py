import asyncio
from uuid import uuid4

from app.core.concurrency import ordered_map
from app.db.models import PipelineRun
from app.integrations.batch_gateway import BatchGateway, BatchingClient
from app.integrations.model_gateway import GatewayError
from app.pipelines.dynamic import (
    DynamicCustomAdapter,
    DynamicDetectionRecognitionAdapter,
    DynamicOfficialAdapter,
    DynamicRecognitionAdapter,
)
from app.services.lean_storage import compact_provenance
from app.services.metrics_service import normalize_text


class PipelineManager:
    def __init__(self, settings):
        self.settings = settings
        self.batches = BatchGateway()
        self.task_slots = asyncio.Semaphore(settings.ocr_max_concurrent_tasks)

    @classmethod
    def requires_crop(cls, pipeline_id):
        return not isinstance(pipeline_id, str) and bool(pipeline_id.execution_mode)

    async def run(self, configs, original_image, cropped_image, roi, roi_source="none"):
        async def run_one(config):
            request_id = f"ocr_{uuid4().hex}"
            adapter_class = None
            if config.execution_mode:
                adapter_class = {
                    "det_rec": DynamicDetectionRecognitionAdapter,
                    "rec": DynamicRecognitionAdapter,
                    "integrated": DynamicCustomAdapter if config.source == "custom" else DynamicOfficialAdapter,
                }[config.execution_mode]
                # Official model selection always runs inside Paddle's OCR API.
                # Also cover saved definitions from the former separate-stage UI.
                if config.source == "official":
                    adapter_class = DynamicOfficialAdapter
            if adapter_class is None:
                return PipelineRun(pipeline_id=config.pipeline_id, pipeline_name=config.name,
                                   status="error", error_code="ADAPTER_NOT_CONFIGURED",
                                   error_message="No adapter is registered for this pipeline", boxes=[], request_id=request_id)
            adapter = adapter_class(config, self.settings)
            if config.source != "official" and config.execution_mode in ("det_rec", "rec"):
                adapter.gateway = BatchingClient(adapter.gateway, self.batches)
            try:
                result = await adapter.run(
                    original_image=original_image,
                    cropped_image=cropped_image if adapter.requires_crop else None,
                    roi=roi,
                    request_id=request_id,
                )
                return PipelineRun(
                    pipeline_id=result.pipeline_id,
                    pipeline_name=result.pipeline_name,
                    status="success",
                    raw_text=result.raw_text if result.raw_text != result.final_text else None,
                    final_text=result.final_text,
                    normalized_text=normalize_text(result.final_text),
                    confidence=result.confidence,
                    processing_time_ms=result.processing_time_ms,
                    boxes=result.boxes,
                    raw_response=compact_provenance(result.raw_response),
                    **result.diagnostics,
                )
            except GatewayError as exc:
                diagnostics = dict(adapter.diagnostics)
                diagnostics["gateway_request_id"] = exc.request_id
                return PipelineRun(
                    pipeline_id=config.pipeline_id,
                    pipeline_name=config.name,
                    status="error",
                    error_message=str(exc),
                    error_code=exc.code,
                    boxes=[],
                    **diagnostics,
                )
            except Exception:
                return PipelineRun(
                    pipeline_id=config.pipeline_id,
                    pipeline_name=config.name,
                    status="error",
                    error_message="Pipeline failed unexpectedly; verify adapter configuration",
                    error_code="PIPELINE_ERROR",
                    boxes=[],
                    **adapter.diagnostics,
                )

        async def bounded(config):
            async with self.task_slots:
                return await run_one(config)

        return await ordered_map(configs, bounded, self.settings.ocr_max_concurrent_tasks)
