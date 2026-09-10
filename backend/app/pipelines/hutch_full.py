from dataclasses import dataclass
from hashlib import sha256

from app.integrations.model_gateway import GatewayError
from app.pipelines.hutch_crop import HutchCropPipelineAdapter


@dataclass(frozen=True)
class FullImageROI:
    png: bytes
    width: int
    height: int
    sha256: str
    roi: dict | None


class HutchFullPipelineAdapter(HutchCropPipelineAdapter):
    """Preserve the full raster and logical ROI; never crop in this application."""

    crop_stage = "external_hutch"

    def prepare_input(self, original_image, cropped_image, roi):
        if cropped_image is not None:
            raise GatewayError(
                "Hutch Full must receive original image and ROI, never a pre-made crop",
                "INVALID_PIPELINE_INPUT",
            )
        if original_image is None:
            raise GatewayError("Hutch Full requires the original image", "INVALID_PIPELINE_INPUT")
        self.images.validate_roi(roi, original_image.width, original_image.height)
        png = self.images.encode_png(original_image)
        return FullImageROI(
            png, original_image.width, original_image.height, sha256(png).hexdigest(),
            dict(roi) if roi else None,
        )

    def build_request(self, source, request_id):
        return self.gateway.build_full_roi_request(
            source=source, endpoint=self.config.endpoint,
            query_params={"engine": "paddle"}, fields=self.model_parameters(),
            request_id=request_id,
        )
