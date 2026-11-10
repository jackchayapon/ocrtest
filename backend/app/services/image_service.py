import io
import warnings
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from hashlib import sha256

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import WORKLOAD_LIMITS, Settings
from app.core.errors import AppError

SUPPORTED_MIMES = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WEBP",
    "image/tiff": "TIFF",
    "image/bmp": "BMP",
}


class _DifferentPNG(Exception):
    pass


class _PNGMatcher:
    """Compare encoder chunks without allocating a second whole-page PNG."""
    def __init__(self, expected):
        self.expected = memoryview(expected)
        self.position = 0

    def write(self, chunk):
        end = self.position + len(chunk)
        if end > len(self.expected) or memoryview(chunk) != self.expected[self.position:end]:
            raise _DifferentPNG
        self.position = end
        return len(chunk)

    def flush(self):
        pass


@dataclass(frozen=True)
class CanonicalCrop:
    png: bytes
    width: int
    height: int
    sha256: str
    _source: Image.Image | None = field(default=None, repr=False, compare=False)
    _roi: tuple[int, int, int, int] | None = field(default=None, repr=False, compare=False)

    @contextmanager
    def pixels(self, images):
        """Borrow only while the caller owns the decoded source; never across HTTP waits."""
        if self._source is None:
            with closing(images.open(self.png)) as image:
                yield image
        elif self._roi is None or self._roi == (0, 0, self._source.width, self._source.height):
            yield self._source
        else:
            roi = dict(zip(("x1", "y1", "x2", "y2"), self._roi))
            with closing(images.crop(self._source, roi)) as image:
                yield image


class ImageService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def validate_dimensions(self, width, height):
        if (min(width, height) < 1 or width * height > self.settings.max_image_pixels
                or max(width, height) > self.settings.max_image_dimension):
            raise AppError(
                f"ภาพเกินขีดจำกัด กรุณาใช้ภาพไม่เกิน {self.settings.max_image_pixels / 1_000_000:g} ล้านพิกเซล "
                f"และด้านละ {self.settings.max_image_dimension} พิกเซล / Image exceeds supported pixel/dimension limits", 413)

    def inspect(self, data):
        """Read dimensions only; never allocate decoded source pixels."""
        try:
            with Image.open(io.BytesIO(data)) as image:
                self.validate_dimensions(*image.size)
                return image.size
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise AppError("Invalid image header / ไม่สามารถอ่านส่วนหัวภาพ", 415) from None

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
                with closing(Image.open(io.BytesIO(data))) as image:
                    if image.format != SUPPORTED_MIMES[mime]:
                        raise AppError("Image contents do not match its MIME type", 415)
                    width, height = image.size
                    self.validate_dimensions(width, height)
                    if getattr(image, "n_frames", 1) > 1:
                        raise AppError("Upload a single image or one document page at a time", 415)
                    image.load()
                    ImageOps.exif_transpose(image, in_place=True)
                    if image.mode == "RGB":
                        return self.encode_png(image), image.width, image.height
                    with closing(image.convert("RGB")) as canonical:
                        return self.encode_png(canonical), canonical.width, canonical.height
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            raise AppError("The uploaded file is not a valid supported image", 415) from None

    @staticmethod
    def encode_png(image: Image.Image, *, reuse: bytes | None = None) -> bytes:
        if reuse is not None:
            matcher = _PNGMatcher(reuse)
            try:
                image.save(matcher, format="PNG")
                if matcher.position == len(reuse):
                    return reuse
            except _DifferentPNG:
                pass
        with io.BytesIO() as output:
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
        with io.BytesIO(data) as buffer:
            image = Image.open(buffer)
            try:
                if (image.width * image.height > WORKLOAD_LIMITS["max_image_pixels"]
                        or max(image.size) > WORKLOAD_LIMITS["max_image_dimension"]):
                    raise AppError("ภาพเกินขีดจำกัดการประมวลผล / Image exceeds processing limits", 413)
                if image.mode == "RGB":
                    image.load()  # Detach the pixels before closing the temporary input.
                    image.format = None  # Match the former convert("RGB") return value.
                    return image
                with closing(image):
                    return image.convert("RGB")
            except BaseException:
                image.close()
                raise

    def crop(self, original: Image.Image, roi: dict | None) -> Image.Image:
        self.validate_roi(roi, original.width, original.height)
        if roi is None:
            return original.copy()
        if original.mode == "RGB" and all(isinstance(roi[k], int) for k in ("x1", "y1", "x2", "y2")):
            # Pillow copies only the ROI; np.asarray(original) copied the entire page.
            region = original.crop(tuple(roi[k] for k in ("x1", "y1", "x2", "y2")))
            region.info.clear()  # Preserve the former Image.fromarray PNG metadata contract.
            return region
        # OpenCV operates on the stored original pixel grid. No rescaling occurs here.
        pixels = np.asarray(original)
        region = pixels[roi["y1"] : roi["y2"], roi["x1"] : roi["x2"]]
        return Image.fromarray(cv2.copyMakeBorder(region, 0, 0, 0, 0, cv2.BORDER_CONSTANT))

    def canonical_crop(self, original: Image.Image, roi: dict | None, *,
                       share_source=False, encoded_source: bytes | None = None) -> CanonicalCrop:
        """One deterministic encoding shared by both crop strategy boundaries."""
        self.validate_roi(roi, original.width, original.height)
        bounds = tuple(roi[k] for k in ("x1", "y1", "x2", "y2")) if roi else None
        # A metadata-free RGB whole-page crop has the exact same PNG encoder input.
        # Keep the metadata/conversion fallback for historical callers and other modes.
        borrow = (original.mode == "RGB" and not original.info
                  and not getattr(original, "encoderinfo", None)
                  and bounds in (None, (0, 0, original.width, original.height)))
        crop = original if borrow else self.crop(original, roi)
        try:
            png = (self.encode_png(crop, reuse=encoded_source)
                   if borrow and encoded_source is not None else self.encode_png(crop))
            # Never infer canonical equivalence from the extension/format. Compare bytes.
            if encoded_source is not None and png == encoded_source:
                png = encoded_source
            return CanonicalCrop(png, crop.width, crop.height, sha256(png).hexdigest(),
                                 original if share_source and original.mode == "RGB" else None, bounds)
        finally:
            if not borrow:
                crop.close()

    @staticmethod
    def rectified_size(polygon):
        quad = np.asarray(polygon, dtype=np.float32)
        if quad.shape != (4, 2) or not np.isfinite(quad).all():
            raise ValueError("Invalid detection quadrilateral")
        width = max(1, round(max(np.linalg.norm(quad[1] - quad[0]), np.linalg.norm(quad[2] - quad[3]))))
        height = max(1, round(max(np.linalg.norm(quad[3] - quad[0]), np.linalg.norm(quad[2] - quad[1]))))
        return width, height

    def rectify_quad(self, image: Image.Image, polygon) -> bytes:
        """Lossless line PNG from a DET quadrilateral ordered TL, TR, BR, BL.

        Used only by the separate Benchmark DET/REC adapter. The canonical ROI
        supplied to detection is never resized or re-encoded here.
        """
        quad = np.asarray(polygon, dtype=np.float32)
        if (quad.shape != (4, 2) or not np.isfinite(quad).all()
                or not cv2.isContourConvex(quad) or abs(cv2.contourArea(quad)) < 1
                or (quad < 0).any() or (quad[:, 0] > image.width).any()
                or (quad[:, 1] > image.height).any()):
            raise ValueError("Invalid detection quadrilateral")
        width, height = self.rectified_size(quad)
        if width * height > self.settings.max_image_pixels or max(width, height) > self.settings.max_image_dimension:
            raise ValueError("Detection crop exceeds image limits")
        target = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
        matrix = cv2.getPerspectiveTransform(quad, target)
        right = min(image.width, int(np.ceil(quad[:, 0].max())) + 4)
        bottom = min(image.height, int(np.ceil(quad[:, 1].max())) + 4)
        if right * bottom <= image.width * image.height // 4:
            # Keep origin(0,0) and the EXACT matrix. Translating a tight bounding
            # box can change OpenCV's fractional rounding and OCR crop pixels.
            # Four extra pixels cover cubic interpolation; no sampled border changes.
            with closing(image.crop((0, 0, right, bottom))) as prefix:
                pixels = cv2.warpPerspective(np.asarray(prefix), matrix, (width, height),
                                             flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        else:
            pixels = cv2.warpPerspective(np.asarray(image), matrix, (width, height),
                                         flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        with closing(Image.fromarray(pixels)) as crop:
            return self.encode_png(crop)
