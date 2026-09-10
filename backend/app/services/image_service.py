import io
import warnings
from dataclasses import dataclass
from hashlib import sha256

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import Settings
from app.core.errors import AppError

SUPPORTED_MIMES = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WEBP",
    "image/tiff": "TIFF",
    "image/bmp": "BMP",
}


@dataclass(frozen=True)
class CanonicalCrop:
    png: bytes
    width: int
    height: int
    sha256: str


class ImageService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def decode_upload(self, data: bytes, mime: str):
        if mime not in SUPPORTED_MIMES:
            raise AppError("Upload PNG, JPEG, WebP, TIFF, or BMP images", 415)
        if not data:
            raise AppError("The uploaded image is empty")
        if len(data) > self.settings.max_upload_mb * 1024 * 1024:
            raise AppError(f"Image exceeds {self.settings.max_upload_mb} MB limit", 413)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    if image.format != SUPPORTED_MIMES[mime]:
                        raise AppError("Image contents do not match its MIME type", 415)
                    width, height = image.size
                    if (
                        width * height > self.settings.max_image_pixels
                        or max(width, height) > self.settings.max_image_dimension
                    ):
                        raise AppError("Image dimensions exceed the configured limit", 413)
                    if getattr(image, "n_frames", 1) > 1:
                        raise AppError("Upload a single image or one document page at a time", 415)
                    image.load()
                    canonical = ImageOps.exif_transpose(image).convert("RGB")
                    encoded = self.encode_png(canonical)
                    return encoded, canonical.width, canonical.height
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            raise AppError("The uploaded file is not a valid supported image", 415) from None

    @staticmethod
    def encode_png(image: Image.Image) -> bytes:
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    @staticmethod
    def validate_roi(roi: dict | None, width: int, height: int):
        if roi is None:
            return
        x1, y1, x2, y2 = (roi[key] for key in ("x1", "y1", "x2", "y2"))
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise AppError("ROI must be inside the original image with positive dimensions", 422)

    @staticmethod
    def open(data: bytes) -> Image.Image:
        with Image.open(io.BytesIO(data)) as image:
            return image.convert("RGB")

    def crop(self, original: Image.Image, roi: dict | None) -> Image.Image:
        self.validate_roi(roi, original.width, original.height)
        if roi is None:
            return original.copy()
        # OpenCV operates on the stored original pixel grid. No rescaling occurs here.
        pixels = np.asarray(original)
        region = pixels[roi["y1"] : roi["y2"], roi["x1"] : roi["x2"]]
        return Image.fromarray(cv2.copyMakeBorder(region, 0, 0, 0, 0, cv2.BORDER_CONSTANT))

    def canonical_crop(self, original: Image.Image, roi: dict | None) -> CanonicalCrop:
        """One deterministic encoding shared by both crop strategy boundaries."""
        crop = self.crop(original, roi)
        try:
            png = self.encode_png(crop)
            return CanonicalCrop(png, crop.width, crop.height, sha256(png).hexdigest())
        finally:
            crop.close()
