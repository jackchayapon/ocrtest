# การพัฒนาและ deployment

## สิ่งที่ deploy

ใช้ frontend/backend images และ persistent uploads พร้อม DATABASE_URL ของ PostgreSQL/Neon ไม่ deploy model weights, source แพลตฟอร์ม Model API, Python venv, host node_modules หรือ test fixtures

Backend เป็น Python 3.12 slim ลง dependencies ตาม requirements-runtime-lock.txt เท่านั้น ใช้ non-root UID 10001 ไม่มี pytest/Ruff ใน runtime Frontend ใช้ Node 24 แบบ multi-stage ส่งเพียง Next standalone/static/public ไป runtime ไม่มี Playwright หรือ test fixtures

Pillow/OpenCV/NumPy ใช้จัดการภาพ, pypdfium2 ใช้ PDF จึงยังเป็น dependencies ที่จำเป็น ไม่มีเหตุผลให้เปลี่ยน stack หรือเพิ่ม local PaddleOCR ใช้ `pip check` และ lockfiles เพื่อทำซ้ำ build

## Environment

ดู [.env.example](../.env.example) สำหรับค่าครบ Backend อ่าน root .env แล้ว backend/.env; process env มีลำดับสูงกว่า DATABASE_URL และ MODEL_GATEWAY_API_KEY เป็น backend-only ค่า NEXT_PUBLIC_API_BASE_URL เป็น URL ที่ **browser** เข้าถึง FastAPI ได้และฝังตอน build

URL/endpoint defaults seed เฉพาะ config ที่ยังไม่มี หากเปลี่ยน env หลังสร้าง records แล้ว ให้ตรวจ Pipeline Settings ด้วย Shared key มีลำดับเหนือ optional per-adapter key; Compose ปัจจุบันส่งเฉพาะ shared Gateway variables ไม่ได้ forward per-adapter overrides

ถ้า DATABASE_URL ว่างจะใช้ PostgreSQL local ของ Compose ไม่ใช้ SQLite เป็น production fallback SQLite ใช้ใน isolated unit tests เท่านั้น เมื่อระบุ Neon แล้วเชื่อมต่อไม่ได้ backend จะแจ้งผิดพลาด ไม่เปลี่ยนฐานเอง

## คำสั่ง Windows

```powershell
docker compose -p ocr-benchmark config --quiet
docker compose -p ocr-benchmark up --build -d --wait
curl.exe -f http://localhost:8000/api/health
curl.exe -f http://localhost:3000
docker compose -p ocr-benchmark exec backend python -m alembic check
```

Docker Desktop ต้องใช้ Linux engine หาก CLI config ใช้งานไม่ได้และ engine อยู่ที่ named pipe ของ Desktop ใช้ `docker --config .docker-local --host npipe:////./pipe/dockerDesktopLinuxEngine compose ...` เป็นตัวเลือกเฉพาะเครื่อง ไม่เปลี่ยน environment ของแอป หลีกเลี่ยงการพิมพ์ resolved compose config/full inspect เพราะอาจมี secrets

Compose bind 3000/8000/5432 เฉพาะ loopback รหัส `ocr_local_dev` ใช้สำหรับ local PostgreSQL เท่านั้น ระบบ server ให้ใช้การป้องกันเครือข่าย/HTTPS ขององค์กร ตั้ง browser API URL และ CORS ให้ตรง deployment ไม่มี login เพิ่มใน MVP

## Migration และ storage

Startup เรียก Alembic upgrade head และ seed เฉพาะ records ที่ขาด Head ปัจจุบัน `0004_real_inputs` migration ไม่ลบเอกสาร/case/prediction/metrics แต่ archive ผลสังเคราะห์เก่าออกจาก product responses/analytics รายละเอียดและการ downgrade อยู่ใน architecture

```powershell
cd backend
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic check
```

สำรองฐานข้อมูลและ uploads คู่กัน ห้าม reset Neon หรือใช้ `docker compose down -v` กับข้อมูลที่ต้องเก็บ Native storage อยู่ backend/storage/uploads; Docker อยู่ volume ที่ /app/storage/uploads สองตำแหน่งนี้ไม่ใช่ชุดเดียวกันแม้ใช้ Neon เดียวกัน หากย้ายการรันให้คัดลอก originals ที่ถูกต้องผ่าน `docker cp` และตรวจ storage_key ก่อนเปิดใช้

ไฟล์ภาพถาวร/PDF ผ่าน StorageService ส่วน crop และ PDF raster อยู่ memory ต้องให้ UID 10001 เขียน mount ได้ ห้าม bake uploads หรือ .env เข้า image

## ตรวจสอบก่อนส่งงาน

รัน `scripts/check.ps1` สำหรับ pytest/Ruff/typecheck/lint/build และเพิ่ม `-Browser` เมื่อกำหนด TEST_DATABASE_URL เป็นฐาน local *_test แล้ว สคริปต์ e2e ใช้ port 8100/3100 และ production Next build พร้อม test-only HTTP interception; ไม่ส่งข้อมูลทดสอบเข้า Neon

ตรวจ health, upload/storage และหน้า browser ของ container หลัง build, ตรวจ missing-key error และไม่พบ product mock generator ใน image การทดสอบ live OCR ต้องรอ key ที่ถูกต้องและสำหรับ Hutch Full ต้องรอ ROI wire contract ด้วย ดู [validation.md](validation.md) สำหรับผลจริงล่าสุด
