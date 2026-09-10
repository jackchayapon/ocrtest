import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from uuid import uuid4

from app.integrations.model_gateway import GatewayError, ModelGatewayClient
from app.pipelines.normalizers import number
from app.services.image_service import CanonicalCrop, ImageService


@dataclass
class PipelineResult:
    pipeline_id: str
    pipeline_name: str
    raw_text: str
    final_text: str
    confidence: float | None
    processing_time_ms: int
    boxes: list[dict] = field(default_factory=list)
    raw_response: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)

    @property
    def text(self):
        return self.final_text


class OCRPipelineAdapter(ABC):
    engine = ""
    detector = ""
    recognizer = "th_PP-OCRv5_mobile_rec"
    crop_stage = "app_crop"

    def __init__(self, config, settings):
        self.config = config
        self.settings = settings
        self.images = ImageService(settings)
        self.gateway = ModelGatewayClient(
            settings, config.base_url, settings.api_key(config.pipeline_id)
        )
        self.diagnostics = {}

    @abstractmethod
    def prepare_input(self, original_image, cropped_image, roi) -> CanonicalCrop: ...

    @abstractmethod
    def parse_response(self, data, *, offset, crop_size): ...

    def model_parameters(self):
        return {}

    def build_request(self, crop: CanonicalCrop, request_id: str):
        # Engine and Hutch parameters are benchmark invariants, not server defaults.
        return self.gateway.build_request(
            png=crop.png,
            endpoint=self.config.endpoint,
            query_params={**(self.config.query_params or {}), "engine": self.engine},
            fields=self.model_parameters(),
            request_id=request_id,
            request_format=self.config.request_format,
        )

    def normalize_result(self, payload, crop, roi, duration):
        offset = (roi["x1"], roi["y1"]) if roi else (0, 0)
        normalized = self.parse_response(
            payload["data"], offset=offset, crop_size=(crop.width, crop.height)
        )
        meta = payload["meta"]

        def trace_text(value, limit):
            return value[:limit] if isinstance(value, str) else None

        gateway_time = number(meta.get("duration_ms"))
        self.diagnostics.update(
            gateway_request_id=trace_text(meta.get("request_id"), 100),
            gateway_duration_ms=gateway_time
            if gateway_time is not None and gateway_time >= 0
            else None,
            gateway_service=trace_text(meta.get("service"), 255),
            gateway_model=trace_text(meta.get("model"), 500),
            detector_model=trace_text(normalized.detector, 255) or self.detector,
            recognizer_model=trace_text(normalized.recognizer, 255) or self.recognizer,
        )
        return PipelineResult(
            self.config.pipeline_id,
            self.config.name,
            normalized.raw_text,
            normalized.final_text,
            normalized.confidence,
            duration,
            normalized.boxes,
            payload,
            dict(self.diagnostics),
        )

    async def run(self, *, original_image=None, cropped_image=None, roi=None, request_id=None):
        started = time.perf_counter()
        request_id = request_id or f"ocr_{uuid4().hex}"
        self.diagnostics = {
            "request_id": request_id,
            "original_width": original_image.width if original_image else None,
            "original_height": original_image.height if original_image else None,
            "roi": roi,
            "crop_stage": self.crop_stage,
            "detector_model": self.detector,
            "recognizer_model": self.recognizer,
        }
        crop = self.prepare_input(original_image, cropped_image, roi)
        self.diagnostics.update(
            input_width=crop.width,
            input_height=crop.height,
            input_sha256=crop.sha256,
            crop_width=crop.width if self.crop_stage == "app_crop" else None,
            crop_height=crop.height if self.crop_stage == "app_crop" else None,
            crop_sha256=crop.sha256 if self.crop_stage == "app_crop" else None,
            input_byte_size=len(crop.png),
            input_format="image/png",
        )
        if not self.config.enabled:
            raise GatewayError("Pipeline is disabled", "PIPELINE_DISABLED")
        if not self.gateway.key:
            raise GatewayError("ยังไม่ได้ตั้งค่า MODEL_GATEWAY_API_KEY จึงไม่สามารถเรียก OCR จริงได้", "MISSING_GATEWAY_KEY")
        payload = await self.gateway.send(self.build_request(crop, request_id))
        return self.normalize_result(
            payload, crop, roi, round((time.perf_counter() - started) * 1000)
        )


class CropInputAdapter(OCRPipelineAdapter):
    def prepare_input(self, original_image, cropped_image, roi):
        if not isinstance(cropped_image, CanonicalCrop):
            raise GatewayError("A canonical pre-adapter crop is required", "INVALID_PIPELINE_INPUT")
        return cropped_image
