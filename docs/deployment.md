# การพัฒนาและ deployment

## Production: Vercel frontend และ backend ที่มี storage ถาวร

Repository: https://github.com/jackchayapon/ocrtest, branch `main` ใช้ Vercel project เดิมถ้ามี ตั้ง Root Directory เป็น `frontend`, Framework เป็น Next.js และใช้ lockfile กับ `npm ci` / `npm run build` ไม่ deploy repository root เป็น FastAPI project

Frontend ต้องมี `NEXT_PUBLIC_API_BASE_URL=<PRODUCTION_BACKEND_HTTPS_URL>` ที่เข้าถึงได้จริงก่อน deploy ห้ามใช้ localhost หรือเดา URL ห้ามใส่ `DATABASE_URL` หรือ `MODEL_GATEWAY_API_KEY` ใน Vercel frontend project

Backend ปัจจุบันใช้ LocalStorageService อ่าน/เขียน original uploads และ PDF ลง STORAGE_PATH เพื่อเปิดประวัติซ้ำ จึงต้องมี persistent disk/volume บน host ที่เหมาะสม ไม่สามารถใช้ filesystem ชั่วคราวของ Vercel Functions เป็น storage ถาวรได้ รอบนี้ไม่เปลี่ยนระบบ storage ดู [ข้อจำกัด runtime ของ Vercel](https://vercel.com/docs/functions/runtimes)

ต้องเตรียม server-side environment ต่อไปนี้บน backend host โดยใช้ private production Neon connection string และ Gateway key ที่หมุนใหม่สำหรับ production ห้ามนำ development key ที่เคยเปิดเผยมาใช้โดยอัตโนมัติ:

```ini
DATABASE_URL=<PRIVATE_PRODUCTION_NEON_CONNECTION_STRING>
MODEL_GATEWAY_BASE_URL=http://107.129.186.30:62051
MODEL_GATEWAY_API_KEY=<FRESH_PRIVATE_PRODUCTION_KEY>
MODEL_GATEWAY_TIMEOUT_SECONDS=240
STORAGE_MODE=local
STORAGE_PATH=<PERSISTENT_VOLUME_MOUNT>/uploads
MAX_UPLOAD_MB=20
MAX_IMAGE_PIXELS=40000000
MAX_IMAGE_DIMENSION=20000
PDF_RENDER_DPI=200
MAX_PDF_PAGES=500
CORS_ORIGINS=<ACTUAL_FRONTEND_PRODUCTION_HTTPS_ORIGIN>
```

ใน Vercel ไป Project → Settings → Environment Variables: ช่อง Name ใส่ `NEXT_PUBLIC_API_BASE_URL` ช่อง Value ใส่ URL จริงอย่างเดียว ไม่ใส่ `NAME=` หรือเครื่องหมายคำพูด เลือก Production แล้ว deploy/redeploy ใหม่หลังแก้ค่า ตาม [เอกสาร environment variables](https://vercel.com/docs/environment-variables) หากตั้ง secrets บน backend platform ก็ใช้ช่อง Value เป็นค่าดิบ ไม่ครอบ quotes และไม่ส่ง secrets ไป Preview โดยไม่จำเป็น

เมื่อได้ frontend URL จริงแล้วเพิ่ม origin นั้นใน CORS_ORIGINS ของ backend ไม่ใช้ wildcard แทนโดเมนที่ยังไม่ทราบ ก่อนประกาศ production พร้อมใช้ ตรวจ frontend `/` และ `/settings/pipelines`, backend `/api/health`, database/storage และ boolean key status โดยไม่พิมพ์ secrets

ยังไม่มี production backend URL หรือการยืนยัน rotated production credentials ใน workspace จึงเตรียม deployment ได้ แต่ยังไม่ควรเผยแพร่ frontend ที่ชี้ localhost หรืออ้างว่าทดสอบ production แล้ว

## สิ่งที่ deploy

ใช้ frontend/backend images และ persistent uploads พร้อม DATABASE_URL ของ PostgreSQL/Neon ไม่ deploy model weights, source แพลตฟอร์ม Model API, Python venv, host node_modules หรือ test fixtures

Backend เป็น Python 3.12 slim ลง dependencies ตาม requirements-runtime-lock.txt เท่านั้น ใช้ non-root UID 10001 ไม่มี pytest/Ruff ใน runtime Frontend ใช้ Node 24 แบบ multi-stage ส่งเพียง Next standalone/static/public ไป runtime ไม่มี Playwright หรือ test fixtures

Pillow/OpenCV/NumPy ใช้จัดการภาพ, pypdfium2 ใช้ PDF จึงยังเป็น dependencies ที่จำเป็น ไม่มีเหตุผลให้เปลี่ยน stack หรือเพิ่ม local PaddleOCR ใช้ `pip check` และ lockfiles เพื่อทำซ้ำ build

## Environment

ดู [.env.example](../.env.example) สำหรับค่าครบ Backend อ่าน root .env แล้ว backend/.env; process env มีลำดับสูงกว่า DATABASE_URL และ MODEL_GATEWAY_API_KEY เป็น backend-only ค่า NEXT_PUBLIC_API_BASE_URL เป็น URL ที่ **browser** เข้าถึง FastAPI ได้และฝังตอน build

ตัวแปรหลักสำหรับ production คือ `MODEL_GATEWAY_BASE_URL`, `MODEL_GATEWAY_API_KEY` และ `MODEL_GATEWAY_TIMEOUT_SECONDS` ทุก Pipeline ใช้ URL และ key ชุดนี้ร่วมกัน ไม่ต้องกำหนดตัวแปรการเชื่อมต่อหรือ credentials ราย Pipeline ส่วน endpoint/engine defaults seed เฉพาะ config ที่ยังไม่มี หากเปลี่ยน env หลังสร้าง records แล้ว ให้ตรวจ Pipeline Settings ด้วย ทุก Pipeline และ Auto ROI ใช้ MODEL_GATEWAY_API_KEY ตัวเดียว ไม่มี fallback key ราย Pipeline; Compose ส่ง key นี้เข้า backend ตอนรันเท่านั้น ไม่ส่งผ่าน build args

ใส่ค่าจริงเฉพาะใน `.env` ส่วนตัว ตัวอย่างต่อไปนี้เป็น placeholders เท่านั้น ส่วน `.env.example` ต้องคง `MODEL_GATEWAY_API_KEY=` ว่างไว้เสมอ:

```ini
DATABASE_URL="YOUR_NEON_CONNECTION_STRING"

MODEL_GATEWAY_BASE_URL=http://107.129.186.30:62051
MODEL_GATEWAY_API_KEY=YOUR_GATEWAY_API_KEY
MODEL_GATEWAY_TIMEOUT_SECONDS=240
```

สำหรับ Gateway token ปัจจุบัน แนะนำ `MODEL_GATEWAY_API_KEY=your_real_gateway_key` โดยไม่ต้องใส่เครื่องหมายคำพูด รูปแบบ `MODEL_GATEWAY_API_KEY="your_real_gateway_key"` ก็ใช้ได้สำหรับ token ทั่วไป เครื่องหมายคำพูดจึงเป็นทางเลือก ไม่ใช่ข้อบังคับ หากมีช่องว่างหรืออักขระพิเศษให้ใช้การครอบค่าตามรูปแบบ dotenv และอย่าเว้นวรรครอบ `=` เช่น หลีกเลี่ยง `MODEL_GATEWAY_API_KEY = abc123` ห้ามคัดลอก key จริง รหัสผ่าน Neon หรือ DATABASE_URL จริงลงเอกสาร

Runtime และ Test Connection ใช้ `settings.model_gateway_base_url` เสมอ ค่า `pipeline_configs.base_url` เดิมเก็บไว้เพื่อ compatibility โดยไม่ใช้เลือกปลายทาง API ส่ง URL ที่มีผลจริงจาก shared environment การแก้ URL ราย Pipeline จึงไม่เปลี่ยนปลายทาง ให้เปลี่ยน `MODEL_GATEWAY_BASE_URL` แล้ว restart backend แทน ไม่ต้องเปลี่ยน schema หรือ reset records

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

ตรวจ health, upload/storage และหน้า browser หลัง build ใช้ MODEL_GATEWAY_API_KEY จาก runtime เท่านั้น Hutch Full ส่งภาพเต็มโดยไม่ใช้ ROI ดูผลจริงล่าสุดใน validation.md
