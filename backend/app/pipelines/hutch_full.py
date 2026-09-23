from dataclasses import dataclass
from hashlib import sha256

from app.integrations.model_gateway import GatewayError
from app.pipelines.hutch_crop import HutchCropPipelineAdapter


@dataclass(frozen=True)
class FullImage:
    png: bytes
    width: int
    height: int
    sha256: str


class HutchFullPipelineAdapter(HutchCropPipelineAdapter):
    """AUTO/legacy/no ROI: full page. Explicit MANUAL ROI: crop inside this adapter."""

    crop_stage = "full_image"
    requires_crop = False

    def prepare_input(self, original_image, cropped_image, roi):
        if cropped_image is not None:
            raise GatewayError(
                "Hutch Full must receive original image, never a pre-made crop",
                "INVALID_PIPELINE_INPUT",
            )
        if original_image is None:
            raise GatewayError("Hutch Full requires the original image", "INVALID_PIPELINE_INPUT")
        if self.crop_stage == "manual_roi":
            if roi is None:
                raise GatewayError("Manual ROI requires coordinates", "INVALID_PIPELINE_INPUT")
            return self.images.canonical_crop(original_image, roi)
        png = self.images.encode_png(original_image)
        return FullImage(
            png, original_image.width, original_image.height, sha256(png).hexdigest(),
        )

    def build_request(self, source, request_id):
        return self.gateway.build_request(
            png=source.png, endpoint=self.config.endpoint,
            query_params={"engine": "paddle"}, fields=self.model_parameters(),
            request_id=request_id, request_format=self.config.request_format,
        )

    async def run(self, *, original_image=None, cropped_image=None, roi=None, request_id=None, roi_source="none"):
        self.crop_stage = "manual_roi" if roi_source == "manual" else "full_image"
        return await super().run(
            original_image=original_image, cropped_image=cropped_image,
            roi=roi if roi_source == "manual" else None, request_id=request_id,
        )
