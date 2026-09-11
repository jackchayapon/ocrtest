# สถาปัตยกรรมแอป

## ขอบเขตระบบ

Frontend Next.js ใช้ canonical API contract เท่านั้น ไม่มี vendor parser, database driver หรือ Gateway key ใน browser Backend FastAPI รับไฟล์ ตรวจ ROI สร้าง input เรียก Gateway และบันทึกผลผ่าน repository

| ส่วน | หน้าที่ |
| --- | --- |
| `frontend/app`, `components`, `lib`, `types` | workspace, Konva viewer, History, Test Detail, Matrix, Analytics, Settings และภาษาไทย |
| `backend/app/api/routes` | HTTP validation และเรียก service |
| `services/test_case_service.py` | จัดการเอกสาร/GT/test case เตรียม crop เฉพาะ Mint/Hutch Crop |
| `services/pipeline_manager.py` | เลือก 3 adapters เรียก concurrent และแยก failure |
| `pipelines/mint.py`, `hutch_crop.py` | รับ CanonicalCrop เดียวกัน ไม่สร้าง crop ซ้ำ |
| `pipelines/hutch_full.py` | FullImage ที่เก็บ raster เต็ม ไม่ใช้ ROI และไม่เรียก crop |
| `integrations/model_gateway.py` | Bearer, multipart, timeout, response validation, redaction, readiness และจุดเชื่อม ROI contract ในอนาคต |
| `pipelines/normalizers.py` | แปลงผล Mint/Paddle เก็บ geometry และใช้ null เมื่อไม่มี confidence |
| `services/image_service.py`, `pdf_service.py` | canonical PNG, SHA-256, render PDF และตรวจขนาด |
| `services/storage_service.py` | เก็บไฟล์ local แยกจาก DB; เปลี่ยนเป็น object storage ได้ภายหลัง |
| `repositories`, `db`, `alembic` | SQLAlchemy 2, psycopg 3, PostgreSQL/Neon, migrations |
| `backend/tests`, `frontend/tests` | test-only HTTP interception/fixtures ไม่รวมใน production images |

## ฐานข้อมูล

ใช้ UUID และ JSONB บน PostgreSQL, `pool_pre_ping=True`, ปิดการแสดง SQL parameters ใน error มีตาราง `documents`, `test_cases`, `pipeline_runs`, `metrics`, `categories`, `test_case_categories`, `pipeline_configs` และ `alembic_version`

`documents` เก็บ storage_key/ขนาด/SHA/PDF metadata; `test_cases` เก็บหน้า/ROI/GT แยกจาก prediction; `pipeline_runs` เก็บข้อความ geometry โมเดล error และ Gateway tracing; `metrics` แยก raw/final; categories เป็น manual labels 14 ประเภท ไม่มีการจำแนกด้วยโมเดล

Migration ตามลำดับ: `0001_benchmark_schema` → `0002_gateway_crop_trace` → `0003_pdf_pages` → `0004_real_inputs` ไม่แก้ประวัติ migration เดิม

Migration ใหม่เปลี่ยน marker ของผลสังเคราะห์เก่าเป็น `archived` และตรวจ marker ใน raw response เพิ่มเติม เก็บทุกแถว/metrics เดิม เพิ่ม input SHA/ขนาดโดย backfill จาก input เก่า ลบเฉพาะตัวเลือก execution mode ที่เลิกใช้ และล้างสถานะ connection ของตัวจำลองเก่า Downgrade คืน schema เก่าและตั้ง config เป็น real ไม่เปิดตัวจำลองเอง; ข้อมูล input tracing ใหม่จะหายตามการ downgrade แต่ prediction เดิมยังอยู่

## ความเป็นธรรมและข้อมูลย้อนหลัง

Mint/Hutch Crop `crop_stage=app_crop` ใช้ crop PNG เดียวกัน Hutch Full `crop_stage=full_image` ใช้ภาพเต็ม ตัว serializer ไม่ส่ง archived runs ออก API ส่วน Matrix/Analytics ตัด archived และ Hutch Full ที่ใช้ semantics เก่าออก เลือกผลล่าสุดต่อ case/pipeline รวม failure ในจำนวน test แต่เฉลี่ยความแม่นยำจากผลสำเร็จที่มี GT เท่านั้น

## ความเป็นส่วนตัว

ไม่เก็บ Base64 ของภาพใน DB ไฟล์ถาวรผ่าน StorageService เท่านั้น crop/page render อยู่ในหน่วยความจำ Responses มี `Cache-Control: private, no-store` ตัว Gateway client ล้าง token/ภาพฝังใน JSON ก่อนเก็บ/ตอบกลับ ไม่ log OCR/GT หรือ request bodies ตามปกติ Compose ปิด access log ของ Uvicorn

ไม่มีโมเดล local, template/CDR/table recognition/SigLIP/YOLO หรือ runtime dependency ต่อ source ของแพลตฟอร์ม Model API
