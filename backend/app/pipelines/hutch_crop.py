from app.pipelines.base import CropInputAdapter
from app.pipelines.normalizers import PaddleResultNormalizer


class HutchCropPipelineAdapter(CropInputAdapter):
    engine = "paddle"
    detector = "PP-OCRv6_medium_det"

    def model_parameters(self):
        return {"text_det_unclip_ratio": 1.7, "text_det_thresh": 0.25, "text_det_box_thresh": 0.6}

    def parse_response(self, data, *, offset, crop_size):
        return PaddleResultNormalizer().normalize(data, offset=offset, crop_size=crop_size)
