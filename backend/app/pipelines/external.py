import re
import time

from app.integrations.external_ocr import ExternalClient, get_provider, normalize_external
from app.integrations.model_gateway import GatewayError
from app.pipelines.base import PipelineResult
from app.services.image_service import CanonicalCrop


class ExternalOCRAdapter:
    requires_crop = True
    crop_stage = "external_api"

    def __init__(self, config, settings):
        self.config, self.settings = config, settings
        self.diagnostics = {}

    async def run(self, *, original_image=None, cropped_image=None, roi=None, request_id=None):
        crop = cropped_image
        if not isinstance(crop, CanonicalCrop):
            raise GatewayError("A canonical crop is required", "INVALID_PIPELINE_INPUT")
        if not self.config.enabled:
            raise GatewayError("Pipeline is disabled", "PIPELINE_DISABLED")
        identity = self.config.integrated_options or {}
        try:
            provider = get_provider(self.settings, identity.get("provider_id"))
        except Exception:
            raise GatewayError("External provider registration is unavailable", "EXTERNAL_NOT_CONFIGURED") from None
        if identity != provider.identity(identity.get("provider_id")):
            raise GatewayError("External provider changed. Review and save the pipeline again.", "EXTERNAL_CONFIG_CHANGED")
        started = time.perf_counter()
        self.diagnostics = dict(request_id=request_id, crop_stage=self.crop_stage, roi=roi,
            original_width=original_image.width if original_image else None,
            original_height=original_image.height if original_image else None,
            input_width=crop.width, input_height=crop.height, input_sha256=crop.sha256,
            input_byte_size=len(crop.png), input_format="image/png", crop_width=crop.width,
            crop_height=crop.height, crop_sha256=crop.sha256)
        payload = await ExternalClient(self.settings, provider).request(request_id, crop.png)
        text, score, boxes, meta = normalize_external(payload, provider, crop, roi)
        trace = meta.get("request_id")
        trace = trace if isinstance(trace, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", trace) else None
        duration = meta.get("duration_ms")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not 0 <= duration <= 600000:
            duration = None
        self.diagnostics.update(gateway_request_id=trace, gateway_duration_ms=duration,
                                gateway_service="external_api", gateway_model=provider.name)
        provenance = {**identity, "geometry_available": bool(boxes)}
        revision = meta.get("model_revision")
        if isinstance(revision, str) and re.fullmatch(r"[a-f0-9]{40}", revision):
            provenance["model_revision"] = revision
        return PipelineResult(self.config.pipeline_id, self.config.name, text, text, score,
            round((time.perf_counter()-started)*1000), boxes,
            {"external_provider": provenance}, dict(self.diagnostics))
