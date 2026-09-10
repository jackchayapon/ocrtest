# OCR Testing & Benchmark App

แอปทดสอบและเปรียบเทียบ OCR จากภาพหรือหน้า PDF ผู้ใช้เลือก ROI กรอก Ground Truth ดูกรอบข้อความและผล CER/WER แล้วเปิดประวัติ ตาราง Matrix และผลแยกประเภทข้อมูลได้ ระบบเรียก OCR ภายนอกเท่านั้น ไม่มีการโหลดโมเดลหรือ GPU ในแอป

## สถาปัตยกรรมและ 3 Pipeline

Next.js/TypeScript/Tailwind/react-konva → FastAPI → Model Gateway ส่วน FastAPI เก็บข้อมูลผ่าน SQLAlchemy 2 + psycopg 3 ไปยัง PostgreSQL/Neon และเก็บไฟล์ผ่าน StorageService แยกจากฐานข้อมูล

| Pipeline | ภาพที่เตรียมและบริการปลายทาง |
| --- | --- |
| Mint | App Crop → `/api/v1/ocr-results?engine=custom` → PP-OCRv5_server_det → ตัดกรอบข้อความในบริการภายนอก → th_PP-OCRv5_mobile_rec |
| Hutch Crop | App Crop → `/api/v1/ocr-results?engine=paddle` → PP-OCRv6_medium_det + th_PP-OCRv5_mobile_rec |
| Hutch Full | ภาพเต็ม/หน้า PDF เต็ม + ROI → adapter ที่ **ไม่ crop ในแอป** → รอสัญญา HTTP ของ external Hutch-side ROI handling |

Mint/Hutch Crop ใช้ PNG ชุดเดียวกัน ค่า Hutch คงที่ `text_det_unclip_ratio=1.7`, `text_det_thresh=0.25`, `text_det_box_thresh=0.6` ปลายทางที่ตั้งใจใช้สำหรับ Hutch Full คือ Paddle เดียวกัน แต่ source ที่ตรวจไม่ยืนยันรูปแบบส่ง ROI จึงคืน `ROI_CONTRACT_UNCONFIRMED` และไม่ส่ง HTTP ที่เดารูปแบบขึ้นมา

Auto ROI ใช้ `/api/v1/document-layouts` เพื่อเสนอกรอบให้ผู้ใช้เลือกเท่านั้น ไม่ใช่ Pipeline ที่สี่ ไม่มีโหมดสร้าง OCR จำลองในผลิตภัณฑ์ เมื่อไม่มี API Key จะคืนข้อผิดพลาดชัดเจน

## สิ่งที่ต้องติดตั้ง

Windows PowerShell, Python 3.12, Node.js 24/npm, PostgreSQL 17 หรือ Neon และ Docker Desktop เมื่อใช้ Docker การทดสอบ browser ใช้ Microsoft Edge บน Windows หรือ Chromium ที่ติดตั้งสำหรับ Playwright

## ตั้งค่าและเริ่มใช้งานบน Windows

รันจากโฟลเดอร์โปรเจกต์ อย่าคัดลอกทับ `.env` ที่มีค่าอยู่แล้ว

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-lock.txt
cd frontend
npm.cmd ci
cd ..
docker compose -p ocr-benchmark up -d postgres
```

ตั้ง `DATABASE_URL` ใน `.env` เป็น Neon connection string โดยคง `sslmode=require` หรือปล่อยว่างเพื่อใช้ PostgreSQL local ที่ Compose เตรียมให้ ห้ามใช้ฐาน production เป็น `TEST_DATABASE_URL` กรอก Gateway key จริงใน `MODEL_GATEWAY_API_KEY` เฉพาะเมื่อได้รับจากผู้ดูแลบริการ

เปิด backend:

```powershell
cd backend
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic check
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

เปิดอีก terminal สำหรับ frontend:

```powershell
cd frontend
npm.cmd run dev
```

หรือหลังติดตั้ง dependencies แล้ว ใช้ `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1` เพื่อเปิดทั้งสองบริการในเบื้องหลัง สคริปต์ตรวจ port/health และพิมพ์ PID กับตำแหน่ง log ออกมา

เปิด `http://localhost:3000` API docs อยู่ที่ `http://localhost:8000/docs` หากเปลี่ยน API URL ให้ใส่เฉพาะ `NEXT_PUBLIC_API_BASE_URL` ใน `frontend/.env.local` แล้ว restart/rebuild frontend ห้ามคัดลอก `.env` ของ backend ไป frontend

## Docker

```powershell
docker compose -p ocr-benchmark config --quiet
docker compose -p ocr-benchmark up --build -d --wait
curl.exe -f http://localhost:8000/api/health
```

Compose อ่าน `.env` เพื่อส่งความลับให้ backend เท่านั้น ใช้ volume แยกสำหรับ PostgreSQL และไฟล์ ห้ามใช้ `down -v` กับข้อมูลที่ต้องการเก็บ รายละเอียดการย้ายไฟล์และตั้งค่าบน server อยู่ใน [คู่มือ deployment](docs/deployment.md)

## การทดสอบ

```powershell
cd backend
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check app tests alembic
cd ../frontend
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
cd ..
```

PostgreSQL/Playwright ใช้ฐานทดสอบ local โดยเฉพาะ สร้างครั้งแรกด้วย `docker compose -p ocr-benchmark exec postgres createdb -U ocr ocr_master_test` จากนั้น:

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://ocr:ocr_local_dev@127.0.0.1:5432/ocr_master_test'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1 -Browser
```

หรือรันเฉพาะ browser ด้วย `scripts/e2e.ps1` แบบเดียวกัน สคริปต์เปิด backend ทดสอบ port 8100, production frontend port 3100 และ intercept เฉพาะ upstream HTTP ใน `backend/tests/e2e_app.py` ซึ่งไม่อยู่ใน production image ผลทดสอบนี้พิสูจน์ workflow และ contract ภายใน ไม่ใช่ความแม่นยำของโมเดลจริง หลัง E2E ให้ build frontend ตาม API URL ใช้งานจริงอีกครั้งก่อนใช้ `npm run start`

## ข้อมูลและข้อจำกัดที่ต้องทราบ

- ภาพเก็บเป็น lossless PNG; PDF เก็บต้นฉบับและ render หน้าที่เลือกตาม DPI ที่บันทึกไว้ ไม่ส่ง PDF ดิบให้ OCR
- ROI อ้างอิงพิกเซลของภาพ/หน้าที่เลือก ขอบขวาและล่างเป็น exclusive ไม่ resize หรือ enhance โดยเงียบ ๆ
- Ground Truth แยกจาก prediction; NFC, trim และรวม whitespace เท่านั้น CER เป็นหลักสำหรับภาษาไทย WER ปัจจุบันแบ่งคำด้วย whitespace
- migration `0004_real_inputs` เก็บผลสังเคราะห์เก่าไว้แต่ไม่แสดง/รวมสถิติ ไม่ลบเอกสารหรือข้อความย้อนหลัง ผล Hutch Full เก่าที่เคยใช้ภาพ crop ไม่รวมในสถิติของนิยามใหม่
- Live OCR ยังต้องใช้ key และบริการที่พร้อมใช้งาน Hutch Full ยังต้องยืนยัน ROI wire contract เพิ่มเติม
- ไม่มี login ใน MVP ใช้บนเครื่อง/เครือข่ายที่เชื่อถือได้หรือภายใต้ระบบควบคุมการเข้าถึงขององค์กร

อ่านต่อ: [API](docs/api.md) · [Flow](docs/flow.md) · [Architecture](docs/architecture.md) · [Gateway](docs/model-gateway.md) · [ผลตรวจสอบ](docs/validation.md)
