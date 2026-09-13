import re

from sqlalchemy.engine import make_url

from app.db.models import AppLog

EVENTS = {
    "document_uploaded": "อัปโหลดเอกสารแล้ว",
    "pdf_page_selected": "เลือกหน้า PDF",
    "test_case_created": "สร้างชุดทดสอบแล้ว",
    "roi_updated": "แก้ไข ROI แล้ว",
    "ground_truth_updated": "แก้ไข Ground Truth แล้ว",
    "categories_updated": "แก้ไขประเภทข้อมูลแล้ว",
    "auto_roi_requested": "เริ่มค้นหา ROI",
    "auto_roi_success": "ค้นหา ROI สำเร็จ",
    "auto_roi_error": "ค้นหา ROI ไม่สำเร็จ",
    "ocr_run_started": "เริ่ม OCR",
    "ocr_run_success": "OCR สำเร็จ",
    "ocr_run_error": "OCR ผิดพลาด",
    "history_deleted": "ลบประวัติการทดสอบแล้ว เก็บเอกสารต้นฉบับไว้",
    "batch_started": "เริ่มประมวลผลหน้าที่เลือก",
    "page_started": "เริ่มประมวลผลหน้า",
    "page_success": "ประมวลผลหน้าสำเร็จ",
    "page_error": "ประมวลผลหน้าผิดพลาด",
    "batch_finished": "จบการประมวลผลหน้าที่เลือก",
}


class LogService:
    def __init__(self, session, settings):
        self.session, self.settings = session, settings

    def add(self, event_type, *, case=None, run=None, document_id=None, page_number=None,
            request_id=None, gateway_request_id=None, error_code=None, count=None):
        if event_type not in EVENTS:
            raise ValueError("Unknown application event")

        def identifier(value):
            if not isinstance(value, str):
                return None
            secrets = (self.settings.model_gateway_api_key.get_secret_value(),
                       self.settings.database_url.get_secret_value(),
                       make_url(self.settings.sqlalchemy_url).password)
            if any(secret and secret in value for secret in secrets):
                return None
            return value if re.fullmatch(r"[A-Za-z0-9_:-]{1,100}", value) else None

        metadata = {}
        code = identifier(error_code or (run.error_code if run else None))
        if code:
            metadata["error_code"] = code
        if type(count) is int:
            metadata["count"] = count
        if run and run.processing_time_ms is not None:
            metadata["duration_ms"] = run.processing_time_ms
        record = AppLog(
            event_type=event_type, message=EVENTS[event_type],
            level="ERROR" if event_type.endswith("error") else "INFO",
            test_case_id=case.id if case else None,
            document_id=case.document_id if case else document_id,
            page_number=case.page_number if case else page_number,
            pipeline_id=run.pipeline_id if run else None,
            request_id=identifier(run.request_id if run else request_id),
            gateway_request_id=identifier(run.gateway_request_id if run else gateway_request_id),
            details=metadata,
        )
        self.session.add(record)
        return record
