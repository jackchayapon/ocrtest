from app.pipelines.base import CropInputAdapter
from app.pipelines.normalizers import MintResultNormalizer


class MintPipelineAdapter(CropInputAdapter):
    """Call the Gateway's complete DET/crop/REC implementation with the shared crop."""

    engine = "custom"
    detector = "PP-OCRv5_server_det"

    def parse_response(self, data, *, offset, crop_size):
        return MintResultNormalizer().normalize(data, offset=offset, crop_size=crop_size)
