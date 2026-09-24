# หลายหน้า PDF ประวัติ และบันทึกกิจกรรม

## Gateway response limit

`MODEL_GATEWAY_MAX_RESPONSE_MB=64` เป็น backend-only configuration แยกจาก MAX_UPLOAD_MB และ MAX_IMAGE_PIXELS ค่าเป็น MiB (1024×1024 bytes) ต้องอยู่ระหว่าง 1–256 ไม่อนุญาต unlimited

ModelGatewayClient นับ response bytes ขณะ stream ก่อน parse JSON เมื่อเกินกำหนดคืน RESPONSE_TOO_LARGE พร้อมข้อความ “ผลลัพธ์ที่ Gateway ส่งกลับมีขนาดใหญ่เกินขีดจำกัด 64 MB” (ตัวเลขตาม configuration) ไม่กล่าวว่าภาพ upload ใหญ่เกินไป Heavy image payload ยังคงถูก redact ก่อน persist และ Gateway metadata ยังคงเก็บตามเดิม

## เลือกหลายหน้า

ในหน้า workspace หลังอัปโหลด PDF มีช่องช่วงหน้า เช่น `1, 3, 5-8`, checkbox, เลือกทุกหน้า, ล้างหน้า และจำนวนหน้าที่เลือก ไม่ render thumbnails/full-page rasters ทั้งไฟล์พร้อมกัน พรีวิวเดิมโหลดเฉพาะหน้าที่ผู้ใช้เลือกดู

ปุ่ม “ประมวลผลหน้าที่เลือก” ใช้ Pipeline และประเภทข้อมูลที่เลือกใน workspace กับ **test case ใหม่ทุกหน้า** โดยตั้ง full-page ROI ให้ crop-based adapters ทั้งสี่ และ Ground Truth เริ่มเป็น null; ไม่เปลี่ยน ROI/GT ของ test case เดิม Hutch Full รับภาพเต็มโดยไม่มี ROI เช่นเดิม

```http
POST /api/documents/{document_id}/run-pages
Content-Type: application/json
```

```json
{"pages":[3,1,2,1],"pipelines":["mint","hutch_crop","hutch_full"],"category_codes":["thai_text","blur"]}
```

หมายเลขหน้าต้องเป็น integer ภายในจำนวนหน้าจริง รายการซ้ำจะถูกตัดและเรียงเป็น `[1,2,3]` ข้อผิดพลาด validation คืน 422 ก่อนเริ่ม stream

ตอบกลับ `application/x-ndjson` ทีละ event: batch_started → page_started → page_success/page_error → … → batch_finished มี page, status และ test_case_id ของหน้าที่บันทึกแล้ว UI แสดง รอดำเนินการ/กำลังประมวลผล/สำเร็จ/ผิดพลาด และลิงก์เปิดผลรายหน้า

Backend await ทั้งหมดของหน้าปัจจุบันและ commit ก่อนเริ่มหน้าถัดไป ไม่มี gather ข้ามหน้า ภายในหนึ่งหน้ายังคง concurrency ของ pipelines ที่เลือกจาก configuration ใช้ lock ร่วมกับการรันเดี่ยว, Auto ROI และการลบภายใน FastAPI หนึ่ง worker ตาม runtime ปัจจุบัน ไม่รองรับการเพิ่มหลาย worker/replica โดยไม่มี distributed coordination

เมื่อ Pipeline ของหน้าหนึ่งผิดพลาด เก็บ partial results แล้วไปหน้าถัดไป ข้อผิดพลาดระดับหน้าไม่ลบผลก่อนหน้า ปุ่มลองหน้าที่ผิดพลาดใหม่สร้าง test cases ใหม่เพื่อเก็บประวัติเดิม หากปิดแท็บ/การเชื่อมต่อขาด อาจหยุด batch ที่ยังไม่เริ่ม ให้ตรวจ History/Logs ก่อนลองใหม่ ไม่มี background queue หรือ resume job อัตโนมัติ

## ประเภทข้อมูล

Categories เป็น metadata หลายค่า ไม่ถูกส่งเป็น model hints แก้ได้แยกทุก test case หลัง batch การวิเคราะห์ใช้ผลล่าสุดต่อ pipeline/case แสดงจำนวนตัวอย่าง, success/error count, CER/WER/Exact Match เมื่อมี GT, เวลาเฉลี่ย และ confidence ที่โมเดลส่งมา ไม่สร้างค่าทดแทนเมื่อ GT/confidence ไม่มี

## ลบประวัติ

`DELETE /api/test-cases/{id}` คืน 204 หรือ 404 เมื่อไม่พบ มี confirmation modal ใน History ก่อนเรียก API ลบ test case, pipeline runs, metrics และ category joins ภายใน transaction เดียว หาก commit ล้มเหลว rollback ทั้งหมด

**เก็บ Document และไฟล์ต้นฉบับเสมอ** แม้ไม่เหลือ test cases เพื่อไม่ลบ PDF ที่ใช้หลายหน้าโดยไม่ตั้งใจ ไม่ลบ category definitions และไม่ลบ audit logs ไม่มี orphan-document cleanup หรือ bulk-delete ในรอบนี้

## Logs

Migration `0005_app_logs` เพิ่ม `app_logs` เท่านั้น ไม่แก้ migration เดิม Audit IDs ไม่มี cascading FK เพื่อให้บันทึกการลบยังตรวจย้อนหลังได้

`GET /api/logs` เรียงใหม่ไปเก่า รองรับ `level`, `event_type`, `pipeline`, `request_id` (ค้นหาบางส่วน), `test_case_id`, `date_from`, `date_to`, `limit` (1–100, default 25), `offset` คืน `{total, items}`

หน้า `/logs` มีตัวกรองและ pagination; Test Detail มีลิงก์ดู logs เฉพาะ test case เหตุการณ์ที่บันทึก:

- document_uploaded, pdf_page_selected, test_case_created
- roi_updated, ground_truth_updated, categories_updated
- auto_roi_requested, auto_roi_success, auto_roi_error
- ocr_run_started, ocr_run_success, ocr_run_error
- history_deleted
- batch_started, page_started, page_success, page_error, batch_finished

ระดับเหตุการณ์ปกติ INFO และความล้มเหลว ERROR รองรับตัวกรอง WARNING ด้วย เก็บเฉพาะข้อความมาตรฐาน, IDs, หน้า, Pipeline, request IDs, error code และ duration/count ที่อนุญาต ไม่เก็บชื่อไฟล์ผู้ใช้, OCR/GT text, raw Gateway response, image/PDF/Base64, Authorization หรือ credentials

ไม่มี background retention worker แนะนำ retention 30 วันโดยนโยบายผู้ดูแลฐานข้อมูล ไม่ให้หน้าเว็บอ่าน logs ทั้งตารางครั้งเดียว

## ตรวจสอบ

ใช้ PostgreSQL local `*_test` สำหรับ migration/tests; ห้ามตั้ง TEST_DATABASE_URL เป็น Neon production รันทดสอบผ่าน scripts/check.ps1 และ scripts/e2e.ps1 ตาม README การทดสอบขนาด response ใช้ httpx test transport เท่านั้น ไม่ส่ง response ใหญ่ไป Gateway จริง
