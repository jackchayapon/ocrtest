import re
from hashlib import sha256

from sqlalchemy import delete, select

from app.core.errors import AppError
from app.db.models import Document, Metric, TestCase, new_id, now
from app.repositories.benchmark_repository import BenchmarkRepository
from app.services.field_service import FieldService
from app.services.image_service import ImageService
from app.services.log_service import LogService
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
        self.logs = LogService(session, settings)

    def upload(self, data: bytes, filename: str, mime: str, document_type_id=None) -> Document:
        if document_type_id:
            from app.services.document_type_service import active_type
            active_type(self.repository.session, document_type_id)
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
            document_type_id=document_type_id,
            page_count=first.page_count if is_pdf else 1,
            pdf_render_dpi=self.settings.pdf_render_dpi if is_pdf else None,
            width=width,
            height=height,
            storage_key=key,
            sha256=sha256(encoded).hexdigest(),
        )
        try:
            self.logs.add("document_uploaded", document_id=document_id)
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
        if not roi and data.roi_source != "none":
            raise AppError("ROI source requires a selected ROI", 422)
        record = TestCase(
            id=new_id(),
            document=document,
            page_number=page_number,
            page_width=width if page_number else None,
            page_height=height if page_number else None,
            roi=roi,
            roi_source=data.roi_source,
            ground_truth_raw=data.ground_truth_raw,
            ground_truth_normalized=normalize_text(data.ground_truth_raw)
            if data.ground_truth_raw is not None
            else None,
            categories=self.repository.categories(data.category_codes),
            status="draft",
            workflow=data.workflow,
        )
        record.document_id = document.id
        self.logs.add("test_case_created", case=record)
        if page_number:
            self.logs.add("pdf_page_selected", case=record)
        return self.repository.save(record)

    def update(self, case_id, data):
        from app.services.ocr_jobs import ensure_not_running
        ensure_not_running(self.repository.session, case_id)
        record = self.repository.test_case(case_id, for_update=True)
        if record.workflow == "global" and ({"roi", "roi_source", "ground_truth_raw"} & data.model_fields_set):
            raise AppError("Use Global Layout and Global Field Ground Truth endpoints", 409)
        if {"roi", "roi_source"} & data.model_fields_set:
            roi = (data.roi.model_dump() if data.roi else None) if "roi" in data.model_fields_set else record.roi
            source = data.roi_source if "roi_source" in data.model_fields_set else (record.roi_source if roi else "none")
            if not roi and source != "none":
                raise AppError("ROI source requires a selected ROI", 422)
            self.images.validate_roi(
                roi,
                record.page_width or record.document.width,
                record.page_height or record.document.height,
            )
            if record.runs and (roi != record.roi or source != record.roi_source):
                raise AppError(
                    "Create a new test case to change the ROI after OCR runs; historical predictions must keep their original region",
                    409,
                )
            if roi != record.roi and record.status == "confirmed":
                record.status = "tested" if record.runs else "draft"
            record.roi = roi
            record.roi_source = source
            self.logs.add("roi_updated", case=record)
        if "category_codes" in data.model_fields_set and data.category_codes is not None:
            record.categories = self.repository.categories(data.category_codes)
            self.logs.add("categories_updated", case=record)
        if "ground_truth_raw" in data.model_fields_set:
            self._set_ground_truth(record, data.ground_truth_raw, False)
            self.logs.add("ground_truth_updated", case=record)
        record.updated_at = now()
        return self.repository.save(record)

    def ground_truth(self, case_id, data):
        record = self.repository.test_case(case_id, for_update=True)
        if record.workflow == "global":
            from app.services.global_layout_service import GlobalLayoutService
            return GlobalLayoutService(self).save_document_gt(case_id, data)
        self._set_ground_truth(record, data.ground_truth_raw, data.confirmed)
        self.logs.add("ground_truth_updated", case=record)
        return self.repository.save(record)

    def delete(self, case_id):
        from app.services.ocr_jobs import ensure_not_running
        ensure_not_running(self.repository.session, case_id)
        session = self.repository.session
        record = self.repository.test_case(case_id)
        try:
            self.logs.add("history_deleted", case=record)
            session.delete(record)
            session.commit()
        except Exception:
            session.rollback()
            raise

    def bulk_delete(self, ids):
        session = self.repository.session
        ids = set(ids)
        try:
            found = set(session.scalars(select(TestCase.id).where(TestCase.id.in_(ids)).with_for_update()))
            from app.services.ocr_jobs import has_active_jobs
            if has_active_jobs(session, found):
                raise AppError("An OCR job is active for a selected test case", 409)
            # Schema FK cascades remove exactly the same owned rows as ORM individual delete.
            session.execute(delete(TestCase).where(TestCase.id.in_(found)), execution_options={"synchronize_session": False})
            session.commit()
            return dict(requested=len(ids), deleted=len(found), already_missing=len(ids - found))
        except Exception:
            session.rollback()
            raise

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
        run.error_events.clear()
        if run.status != "success" or ground_truth is None:
            run.metric_records.clear()
            return
        existing = {item.text_kind: item for item in run.metric_records}
        for text_kind, text in (("raw", run.raw_text if run.raw_text is not None else run.final_text), ("final", run.final_text)):
            values = calculate_metrics(text or "", ground_truth)
            if text_kind in existing:
                for key, value in values.items():
                    setattr(existing[text_kind], key, value)
            else:
                run.metric_records.append(Metric(text_kind=text_kind, **values))

    async def run(self, case_id, pipeline_ids, *, checkpoint=None):
        record = self.repository.test_case(case_id)
        if record.workflow == "global":
            from app.services.global_layout_service import GlobalLayoutService
            return await GlobalLayoutService(self).run(case_id, pipeline_ids, checkpoint=checkpoint)
        if checkpoint is not None:
            return await self._run_job_legacy(record, checkpoint)
        configs = [self.repository.config(pipeline_id) for pipeline_id in pipeline_ids]
        self.logs.add("ocr_run_started", case=record)
        self.repository.session.commit()
        page_data, _, _ = self.page_image(record.document, record.page_number)
        original = self.images.open(page_data)
        try:
            crop = (
                self.images.canonical_crop(original, record.roi)
                if any(PipelineManager.requires_crop(config) for config in configs)
                else None
            )
            runs = await PipelineManager(self.settings).run(configs, original, crop, record.roi, record.roi_source)
        finally:
            original.close()
        # Re-read ground truth after external requests; do not evaluate against stale user edits.
        self.repository.session.refresh(
            record, attribute_names=["ground_truth_raw", "ground_truth_normalized", "status"], with_for_update=True
        )
        for run in runs:
            run.test_case_id = record.id
            FieldService.generate(run)
            self.evaluate(run, record.ground_truth_raw)
            record.runs.append(run)
            self.logs.add("ocr_run_success" if run.status == "success" else "ocr_run_error", case=record, run=run)
        if record.status != "confirmed":
            record.status = "tested"
        record.updated_at = now()
        self.repository.save(record)
        return runs

    async def _run_job_legacy(self, record, checkpoint):
        """Checkpoint each legacy pipeline without changing its ROI/metric semantics."""
        from app.db.models import PipelineRun
        session = self.repository.session
        parents = [session.get(PipelineRun, rid) for rid in checkpoint.job.run_ids.values()]
        page_data, _, _ = self.page_image(record.document, record.page_number)
        with self.images.open(page_data) as original:
            manager = PipelineManager(self.settings)
            for config in checkpoint.configs:
                if any(p.pipeline_id == config.pipeline_id for p in parents):
                    continue
                crop = self.images.canonical_crop(original, record.roi) if manager.requires_crop(config) else None
                result = (await manager.run([config], original, crop, record.roi, record.roi_source))[0]
                checkpoint.fence()
                session.refresh(record, attribute_names=["ground_truth_raw", "status"])
                FieldService.generate(result)
                self.evaluate(result, record.ground_truth_raw)
                record.runs.append(result)
                session.flush()
                parents.append(result)
                checkpoint.save(parents)
        if record.status != "confirmed":
            record.status = "tested"
        checkpoint.fence()
        session.commit()
        return parents

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
