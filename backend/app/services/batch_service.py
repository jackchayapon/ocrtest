from app.core.errors import AppError
from app.schemas.contracts import TestCaseCreate
from app.services.test_case_service import TestCaseService


class BatchService:
    """One process owns one page at a time; no cross-page gather or background job."""

    def __init__(self, session, settings, storage):
        self.cases = TestCaseService(session, settings, storage)
        self.session = session

    def validate(self, document_id, data):
        document = self.cases.repository.document(document_id)
        if document.document_type != "pdf":
            raise AppError("การเลือกหลายหน้าใช้ได้เฉพาะ PDF", 422)
        if any(page > document.page_count for page in data.pages):
            raise AppError("หมายเลขหน้าเกินจำนวนหน้า PDF", 422)
        self.cases.repository.categories(data.category_codes)
        for pipeline in data.pipelines:
            self.cases.repository.config(pipeline)

    async def run(self, document_id, data):
        self.cases.logs.add("batch_started", document_id=document_id, count=len(data.pages))
        self.session.commit()
        yield {"event": "batch_started", "pages": data.pages}
        for page in data.pages:
            record = None
            self.cases.logs.add("page_started", document_id=document_id, page_number=page)
            self.session.commit()
            yield {"event": "page_started", "page": page, "status": "running"}
            try:
                # Always create a new independent whole-page case, never mutate a manual case.
                record = self.cases.create(TestCaseCreate(
                    document_id=document_id, page_number=page, category_codes=data.category_codes,
                ))
                record.roi = {"x1": 0, "y1": 0, "x2": record.page_width, "y2": record.page_height}
                self.session.commit()
                runs = await self.cases.run(record.id, data.pipelines)
                success = all(run.status == "success" for run in runs)
                event = "page_success" if success else "page_error"
                self.cases.logs.add(event, case=record)
                self.session.commit()
                yield {"event": event, "page": page, "test_case_id": record.id,
                       "status": "success" if success else "error"}
            except Exception:
                self.session.rollback()
                self.cases.logs.add("page_error", document_id=document_id, page_number=page,
                                    error_code="PAGE_PROCESSING_ERROR")
                self.session.commit()
                yield {"event": "page_error", "page": page, "status": "error",
                       "test_case_id": record.id if record else None,
                       "message": "ประมวลผลหน้านี้ไม่สำเร็จ กรุณาลองใหม่"}
            finally:
                self.session.expunge_all()
        self.cases.logs.add("batch_finished", document_id=document_id, count=len(data.pages))
        self.session.commit()
        yield {"event": "batch_finished"}
