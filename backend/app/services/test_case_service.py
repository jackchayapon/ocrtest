import re
from hashlib import sha256

from app.core.errors import AppError
from app.db.models import Document, Metric, TestCase, new_id, now
from app.repositories.benchmark_repository import BenchmarkRepository
from app.services.image_service import ImageService
from app.services.metrics_service import calculate_metrics, normalize_text
from app.services.pdf_service import PdfService
from app.services.pipeline_manager import PipelineManager


class TestCaseService:
    def __init__(self, session, settings, storage):
        self.repository = BenchmarkRepository(session)
        self.settings = settings
        self.storage = storage
        self.images = ImageService(settings)
        self.pdfs = PdfService(settings)

    def upload(self, data: bytes, filename: str, mime: str) -> Document:
        is_pdf = mime == "application/pdf" or (
            mime in {"", "application/octet-stream"} and filename.lower().endswith(".pdf")
        )
        if is_pdf:
            first = self.pdfs.render(data, 1)
            encoded, width, height = data, first.width, first.height
        else:
            encoded, width, height = self.images.decode_upload(data, mime)
        filename = (
            re.sub(r"[\x00-\x1f\x7f]", "", filename.replace("\\", "/").split("/")[-1]).strip()[:255]
            or "document.png"
        )
        document_id = new_id()
        key = f"{document_id}.{'pdf' if is_pdf else 'png'}"
        self.storage.put(key, encoded)
        record = Document(
            id=document_id,
            filename=filename,
            mime_type="application/pdf" if is_pdf else "image/png",
            document_type="pdf" if is_pdf else "image",
            page_count=first.page_count if is_pdf else 1,
            pdf_render_dpi=self.settings.pdf_render_dpi if is_pdf else None,
            width=width,
            height=height,
            storage_key=key,
            sha256=sha256(encoded).hexdigest(),
        )
        try:
            return self.repository.save(record)
        except Exception:
            self.storage.delete(key)
            raise

    def create(self, data):
        document = self.repository.document(str(data.document_id))
        page_number = self.page_number(document, data.page_number)
        _, width, height = self.page_image(document, page_number)
        roi = data.roi.model_dump() if data.roi else None
        self.images.validate_roi(roi, width, height)
        record = TestCase(
            document=document,
            page_number=page_number,
            page_width=width if page_number else None,
            page_height=height if page_number else None,
            roi=roi,
            ground_truth_raw=data.ground_truth_raw,
            ground_truth_normalized=normalize_text(data.ground_truth_raw)
            if data.ground_truth_raw is not None
            else None,
            categories=self.repository.categories(data.category_codes),
            status="draft",
        )
        return self.repository.save(record)

    def update(self, case_id, data):
        record = self.repository.test_case(case_id)
        if "roi" in data.model_fields_set:
            roi = data.roi.model_dump() if data.roi else None
            self.images.validate_roi(
                roi,
                record.page_width or record.document.width,
                record.page_height or record.document.height,
            )
            if record.runs and roi != record.roi:
                raise AppError(
                    "Create a new test case to change the ROI after OCR runs; historical predictions must keep their original region",
                    409,
                )
            record.roi = roi
        if "category_codes" in data.model_fields_set and data.category_codes is not None:
            record.categories = self.repository.categories(data.category_codes)
        if "ground_truth_raw" in data.model_fields_set:
            self._set_ground_truth(record, data.ground_truth_raw, False)
        record.updated_at = now()
        return self.repository.save(record)

    def ground_truth(self, case_id, data):
        record = self.repository.test_case(case_id)
        self._set_ground_truth(record, data.ground_truth_raw, data.confirmed)
        return self.repository.save(record)

    def _set_ground_truth(self, record, text, confirmed):
        record.ground_truth_raw = text
        record.ground_truth_normalized = normalize_text(text) if text is not None else None
        record.status = "confirmed" if confirmed else ("tested" if record.runs else "draft")
        record.updated_at = now()
        for run in record.runs:
            if not run.archived:
                self.evaluate(run, text)

    @staticmethod
    def evaluate(run, ground_truth):
        if run.status != "success" or ground_truth is None:
            run.metric_records.clear()
            return
        existing = {item.text_kind: item for item in run.metric_records}
        for text_kind, text in (("raw", run.raw_text), ("final", run.final_text)):
            values = calculate_metrics(text or "", ground_truth)
            if text_kind in existing:
                for key, value in values.items():
                    setattr(existing[text_kind], key, value)
            else:
                run.metric_records.append(Metric(text_kind=text_kind, **values))

    async def run(self, case_id, pipeline_ids):
        record = self.repository.test_case(case_id)
        configs = [self.repository.config(pipeline_id) for pipeline_id in pipeline_ids]
        page_data, _, _ = self.page_image(record.document, record.page_number)
        original = self.images.open(page_data)
        try:
            crop = (
                self.images.canonical_crop(original, record.roi)
                if any(config.pipeline_id != "hutch_full" for config in configs)
                else None
            )
            runs = await PipelineManager(self.settings).run(configs, original, crop, record.roi)
        finally:
            original.close()
        # Re-read ground truth after external requests; do not evaluate against stale user edits.
        self.repository.session.refresh(
            record, attribute_names=["ground_truth_raw", "ground_truth_normalized", "status"]
        )
        for run in runs:
            self.evaluate(run, record.ground_truth_raw)
            record.runs.append(run)
        if record.status != "confirmed":
            record.status = "tested"
        record.updated_at = now()
        self.repository.save(record)
        return runs

    @staticmethod
    def page_number(document, page_number):
        if document.document_type != "pdf":
            if page_number is not None:
                raise AppError("ไฟล์ภาพไม่มีหมายเลขหน้า PDF", 422)
            return None
        page_number = 1 if page_number is None else page_number
        if type(page_number) is not int or not 1 <= page_number <= document.page_count:
            raise AppError("ไม่พบหน้าที่เลือกในเอกสาร PDF", 422)
        return page_number

    def page_image(self, document, page_number=None):
        page_number = self.page_number(document, page_number)
        data = self.storage.read(document.storage_key)
        if page_number is not None:
            page = self.pdfs.render(data, page_number, document.pdf_render_dpi)
            return page.png, page.width, page.height
        return data, document.width, document.height

    def page_metadata(self, document_id, page_number=None):
        from app.services.serializers import document_json

        document = self.repository.document(document_id)
        selected = self.page_number(document, page_number)
        _, width, height = self.page_image(document, selected)
        return document_json(document, selected, (width, height))

    def image_bytes(self, document_id, roi=None, page_number=None):
        document = self.repository.document(document_id)
        data, width, height = self.page_image(document, page_number)
        if roi is None:
            return data
        self.images.validate_roi(roi, width, height)
        original = self.images.open(data)
        crop = self.images.crop(original, roi)
        try:
            return self.images.encode_png(crop)
        finally:
            crop.close()
            original.close()
