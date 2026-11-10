"""On-demand PDF rasterization. No OCR, disk cache, or PDF-point ROIs."""

import math
from contextlib import closing
from dataclasses import dataclass
from threading import RLock

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw

from app.core.errors import AppError
from app.core.native_memory import release_native_memory
from app.services.image_service import ImageService

# PDFium is not thread safe, even across different documents. Close every native
# handle under the same process-wide lock; no lazy PDF objects escape this module.
_PDF_LOCK = RLock()


@dataclass(frozen=True)
class PdfPageImage:
    png: bytes
    width: int
    height: int
    page_count: int
    page_number: int


class PdfService:
    def __init__(self, settings):
        self.settings = settings

    def render(self, data: bytes, page_number: int, dpi: int | None = None, *, validate_only=False) -> PdfPageImage | None:
        try:
            return self._render(data, page_number, dpi, validate_only=validate_only)
        finally:
            # PDFium/Pillow handles have closed, including error paths. Returning
            # free native arenas avoids retaining raster peaks for the next OCR.
            release_native_memory()

    def _render(self, data, page_number, dpi=None, *, validate_only=False):
        if len(data) > self.settings.max_upload_mb * 1024 * 1024:
            raise AppError("ไฟล์มีขนาดใหญ่เกินกำหนด", 413)
        if not data.lstrip().startswith(b"%PDF-"):
            raise AppError("ไม่สามารถเปิดไฟล์ PDF นี้ได้ กรุณาตรวจสอบว่าไฟล์ไม่เสียหาย", 415)
        if type(page_number) is not int or page_number < 1:
            raise AppError("กรุณาเลือกหน้าเอกสารตั้งแต่หน้า 1", 422)
        scale = (dpi or self.settings.pdf_render_dpi) / 72
        with _PDF_LOCK:
            try:
                with pdfium.PdfDocument(data) as pdf:
                    if pdfium_raw.FPDF_GetSecurityHandlerRevision(pdf) >= 0:
                        raise AppError("ไฟล์ PDF นี้มีการป้องกันด้วยรหัสผ่าน", 422)
                    count = len(pdf)
                    if count == 0:
                        raise AppError("ไฟล์ PDF นี้ไม่มีหน้าเอกสาร", 422)
                    if count > self.settings.max_pdf_pages:
                        raise AppError("ไฟล์ PDF มีจำนวนหน้าเกินกำหนด", 413)
                    if page_number > count:
                        raise AppError("ไม่พบหน้าที่เลือกในเอกสาร PDF", 422)
                    # API/UI are one-based; the renderer alone uses zero-based indexes.
                    with closing(pdf[page_number - 1]) as page:
                        width, height = (math.ceil(v * scale) for v in page.get_size())
                        try:
                            ImageService(self.settings).validate_dimensions(width, height)
                        except AppError as exc:
                            raise AppError("ขนาดหน้า PDF เกินกำหนด / PDF page: " + exc.message, 413) from None
                        if validate_only:
                            return None
                        with closing(page.render(scale=scale, rev_byteorder=True)) as bitmap:
                            with closing(bitmap.to_pil()) as raster:
                                with closing(raster.convert("RGB")) as rgb:
                                    return PdfPageImage(
                                        ImageService.encode_png(rgb),
                                        rgb.width,
                                        rgb.height,
                                        count,
                                        page_number,
                                    )
            except pdfium.PdfiumError as error:
                if error.err_code == pdfium_raw.FPDF_ERR_PASSWORD:
                    raise AppError("ไฟล์ PDF นี้มีการป้องกันด้วยรหัสผ่าน", 422) from None
                raise AppError(
                    "ไม่สามารถเปิดไฟล์ PDF นี้ได้ กรุณาตรวจสอบว่าไฟล์ไม่เสียหาย", 422
                ) from None
            except (ValueError, OSError, OverflowError):
                raise AppError("ไม่สามารถแสดงหน้าที่เลือกได้ กรุณาลองใหม่อีกครั้ง", 422) from None
