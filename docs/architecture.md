# สถาปัตยกรรมแอป

## ขอบเขตระบบ

Frontend Next.js ใช้ canonical API contract เท่านั้น ไม่มี vendor parser, database driver หรือ Gateway key ใน browser Backend FastAPI รับไฟล์ ตรวจ ROI สร้าง input เรียก Gateway และบันทึกผลผ่าน repository

| ส่วน | หน้าที่ |
| --- | --- |
| `frontend/app`, `components`, `lib`, `types` | workspace, Konva viewer, History, Test Detail, Matrix, Analytics, Settings และภาษาไทย |
| `backend/app/api/routes` | HTTP validation และเรียก service |
| `services/test_case_service.py` | จัดการเอกสาร/GT/test case เตรียม crop ร่วมให้ Mint/Hutch Crop/Benchmark/Thai FT v2 |
| `services/pipeline_manager.py` | เลือกจาก 5 registered adapters เรียก concurrent และแยก failure |
| `pipelines/mint.py`, `hutch_crop.py` | รับ CanonicalCrop เดียวกัน ไม่สร้าง crop ซ้ำ |
| `pipelines/hutch_full.py` | Auto/none ใช้ FullImage; manual สร้าง canonical crop ภายใน adapter |
| `integrations/model_gateway.py` | Bearer, multipart, timeout, response validation, redaction, readiness และตรวจสัญญา DET/REC batch |
| `pipelines/normalizers.py` | แปลงผล Mint/Paddle เก็บ geometry และใช้ null เมื่อไม่มี confidence |
| `services/image_service.py`, `pdf_service.py` | canonical PNG, SHA-256, render PDF และตรวจขนาด |
| `services/storage_service.py` | เก็บไฟล์ local แยกจาก DB; เปลี่ยนเป็น object storage ได้ภายหลัง |
| `repositories`, `db`, `alembic` | SQLAlchemy 2, psycopg 3, PostgreSQL/Neon, migrations |
| `backend/tests`, `frontend/tests` | test-only HTTP interception/fixtures ไม่รวมใน production images |

## ฐานข้อมูล

ใช้ UUID และ JSONB บน PostgreSQL, `pool_pre_ping=True`, ปิดการแสดง SQL parameters ใน error มีตาราง `documents`, `test_cases`, `pipeline_runs`, `metrics`, `categories`, `test_case_categories`, `pipeline_configs` รวม `app_logs`, `ocr_error_events`, `ocr_fields` และ `alembic_version`

`documents` เก็บ storage_key/ขนาด/SHA/PDF metadata; `test_cases` เก็บหน้า/ROI/GT แยกจาก prediction; `pipeline_runs` เก็บข้อความ geometry โมเดล error และ Gateway tracing; `metrics` แยก raw/final; categories เป็น manual labels 14 ประเภท ไม่มีการจำแนกด้วยโมเดล

Migration ตามลำดับ: `0001_benchmark_schema` → `0002_gateway_crop_trace` → `0003_pdf_pages` → `0004_real_inputs` → `0005_app_logs` → `0006_ocr_error_events` → `0007_fields_roi_source` ไม่แก้ประวัติ migration เดิม

Migration 0004 เปลี่ยน marker ของผลสังเคราะห์เก่าเป็น `archived` และตรวจ marker ใน raw response เพิ่มเติม เก็บทุกแถว/metrics เดิม เพิ่ม input SHA/ขนาดโดย backfill จาก input เก่า ลบเฉพาะตัวเลือก execution mode ที่เลิกใช้ และล้างสถานะ connection ของตัวจำลองเก่า Downgrade คืน schema เก่าและตั้ง config เป็น real ไม่เปิดตัวจำลองเอง; ข้อมูล input tracing ใหม่จะหายตามการ downgrade แต่ prediction เดิมยังอยู่

## ความเป็นธรรมและข้อมูลย้อนหลัง

Mint/Hutch Crop/Benchmark/Thai FT v2 `crop_stage=app_crop` ใช้ crop PNG เดียวกัน Hutch Full Auto/none ใช้ `full_image`; manual ใช้ `manual_roi` และ crop ภายใน adapter ตัว serializer ไม่ส่ง archived runs ออก API ส่วน Matrix/Analytics ตัด archived และ Hutch Full ที่ไม่ใช่ full_image ออก (รวม manual_roi ปัจจุบันด้วย เป็นข้อจำกัดที่ต้องแก้แยกจาก cleanup) เลือกผลล่าสุดต่อ case/pipeline รวม failure ในจำนวน test แต่เฉลี่ยความแม่นยำจากผลสำเร็จที่มี GT เท่านั้น

## ความเป็นส่วนตัว

ไม่เก็บ Base64 ของภาพใน DB ไฟล์ถาวรผ่าน StorageService เท่านั้น crop/page render อยู่ในหน่วยความจำ Responses มี `Cache-Control: private, no-store` ตัว Gateway client ล้าง token/ภาพฝังใน JSON ก่อนเก็บ/ตอบกลับ ไม่ log OCR/GT หรือ request bodies ตามปกติ Compose ปิด access log ของ Uvicorn

ไม่มีโมเดล local, template/CDR/table recognition/SigLIP/YOLO หรือ runtime dependency ต่อ source ของแพลตฟอร์ม Model API
