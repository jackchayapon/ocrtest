import asyncio
import time
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
        self.batches = BatchGateway(settings.ocr_gateway_batch_size)
        self.task_slots = asyncio.Semaphore(settings.ocr_max_concurrent_tasks)
        self.windows = {}

    async def run_fields(self, configs, original_image, inputs):
        """Pipeline-major admission coalesces equal queries without unbounded tasks.

        Inputs are a bounded group of (canonical crop, ROI, source). Return field-major
        results in the caller's original config order, including isolated failures.
        """
        async def one(pair):
            config, field = pair
            crop, roi, source = field
            return (await self.run([config], original_image, crop, roi, source))[0]

        results = await ordered_map(
            [(config, field) for config in configs for field in inputs],
            one, self.settings.ocr_max_concurrent_tasks,
        )
        return [[results[c * len(inputs) + f] for c in range(len(configs))]
                for f in range(len(inputs))]

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
                diagnostics["gateway_request_id"] = exc.request_id or diagnostics.get("gateway_request_id")
                return PipelineRun(
                    pipeline_id=config.pipeline_id,
                    pipeline_name=config.name,
                    status="error",
                    error_message=str(exc),
                    error_code=exc.code,
                    raw_response={"failure": {"stage": getattr(adapter, "failure_stage", "gateway_request").replace("_request", "_contract") if exc.code in {"INVALID_RESPONSE", "INVALID_OCR_RESPONSE"} else getattr(adapter, "failure_stage", "gateway_request"), "http_status": exc.http_status}},
                    boxes=[],
                    **diagnostics,
                )
            except Exception as exc:
                return PipelineRun(
                    pipeline_id=config.pipeline_id,
                    pipeline_name=config.name,
                    status="error",
                    error_message="Pipeline failed unexpectedly; verify adapter configuration",
                    error_code="PIPELINE_ERROR",
                    raw_response={"failure": {"stage": getattr(adapter, "failure_stage", "adapter"), "exception_type": type(exc).__name__}},
                    boxes=[],
                    **adapter.diagnostics,
                )

        async def bounded(config):
            async with self.task_slots:
                start = time.perf_counter()
                window = self.windows.setdefault(config.pipeline_id, [start, start])
                try:
                    result = await run_one(config)
                    if result.processing_time_ms is None:
                        result.processing_time_ms = round((time.perf_counter() - start) * 1000)
                    return result
                finally:
                    window[1] = time.perf_counter()

        return await ordered_map(configs, bounded, self.settings.ocr_max_concurrent_tasks)
