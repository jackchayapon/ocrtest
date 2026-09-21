import asyncio
from uuid import uuid4

from app.db.models import PipelineRun
from app.integrations.model_gateway import GatewayError
from app.pipelines.benchmark import BenchmarkPipelineAdapter
from app.pipelines.hutch_crop import HutchCropPipelineAdapter
from app.pipelines.hutch_full import HutchFullPipelineAdapter
from app.pipelines.mint import MintPipelineAdapter
from app.services.metrics_service import normalize_text


class PipelineManager:
    adapter_classes = {
        "mint": MintPipelineAdapter,
        "hutch_crop": HutchCropPipelineAdapter,
        "hutch_full": HutchFullPipelineAdapter,
        "benchmark": BenchmarkPipelineAdapter,
    }

    def __init__(self, settings):
        self.settings = settings

    @classmethod
    def requires_crop(cls, pipeline_id):
        adapter = cls.adapter_classes.get(pipeline_id)
        return adapter is not None and adapter.requires_crop

    async def run(self, configs, original_image, cropped_image, roi):
        async def run_one(config):
            request_id = f"ocr_{uuid4().hex}"
            adapter_class = self.adapter_classes.get(config.pipeline_id)
            if adapter_class is None:
                return PipelineRun(pipeline_id=config.pipeline_id, pipeline_name=config.name,
                                   status="error", error_code="ADAPTER_NOT_CONFIGURED",
                                   error_message="No adapter is registered for this pipeline", boxes=[], request_id=request_id)
            adapter = adapter_class(config, self.settings)
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
                    raw_text=result.raw_text,
                    final_text=result.final_text,
                    normalized_text=normalize_text(result.final_text),
                    confidence=result.confidence,
                    processing_time_ms=result.processing_time_ms,
                    boxes=result.boxes,
                    raw_response=result.raw_response,
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

        return await asyncio.gather(*(run_one(config) for config in configs))
