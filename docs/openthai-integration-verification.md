# ผลการพัฒนาและตรวจสอบ OpenThai External OCR

ตรวจวันที่ 13 พฤศจิกายน 2569 บน branch `feature/openthai-external-ocr` จาก main `3440dbe98a56f38097c4eecf5413d4439d81aa39`

## ขอบเขตที่พัฒนา

- `api/openthai2_ocr_text/` มี FastAPI service, inference, config, security, tests, dependency files, Docker/Compose, model downloader และคู่มือของตนเอง
- Backend เพิ่ม `external_api` ใน PipelineConfig เดิม ใช้ provider registration ฝั่ง Server, transport ที่ตรวจและ pin DNS, adapter และ provenance ที่ปลอดภัย
- Frontend เพิ่ม Internal/External source, เลือก provider ที่อนุมัติแล้ว, แสดง contract/authentication, เปิดปิด Pipeline และ Test Connection
- ใช้ JSON column และ Job snapshot เดิม Schema อยู่ที่ `0012_ocr_jobs` การตรวจ clean migration และ Alembic schema check รวมอยู่ใน Backend suite

ผู้ดูแลจัดการ Endpoint และ Credential ผ่าน environment ฝั่ง Server ผู้ใช้หน้า Settings เลือกรายการที่อนุมัติและปรับชื่อ/สถานะได้ การออกแบบนี้ใช้เส้นทางควบคุม configuration ที่มีอยู่และเหมาะกับ public shared workspace

## ผลทดสอบที่รันจริง

| ชุดตรวจ | ผล | ขอบเขต |
| --- | --- | --- |
| Backend เต็ม | 729 passed, 0 fail/error/skip | PostgreSQL local, migration/schema, durable Jobs, recovery, GT/Metrics, privacy, internal/external adapters |
| External security รอบสุดท้าย | 46 passed, 0 fail/error/skip | รวมกรณี NAT64/site-local ที่เพิ่มหลัง full run, URL/DNS rebinding, redirects, credential echo, timeout, JSON Base64, error isolation |
| Standalone service | 13 passed, 0 fail/error/skip | Reader doubles, actual FastAPI HTTP handling, auth/readiness, invalid/oversized/JPEG input, NumPy, admission, deadline, cleanup, output caps, corrupt snapshot |
| Playwright กลุ่มที่เกี่ยวข้อง | 16 passed, 0 fail/skip | Custom/Official เดิม, approved External Provider, Desktop1440/Mobile390, keyboard, Job recovery และ Comparison |
| Playwright local real inference | 1 passed, 0 fail/skip | Next.js → OCRLab Backend → OpenThai HTTP → โมเดล ONNX จริง, PostgreSQL local |
| TypeScript / ESLint / production build | PASS | รันกับ Frontend candidate |
| Ruff | PASS | Backend app/tests และ standalone app/tests/scripts |
| Diff / Secret scan | PASS | ตรวจ tracked และ proposed files, `.env`/`.runtime`/weights/virtualenv ถูก ignore |
| Docker build/start/restart | PASS | Context เฉพาะ service, UID10001, read-only filesystem/model mount, source hashesตรง8/8 |

Full Backend729 เป็นผลก่อนเพิ่มสองกรณี SSRF ส่วน security suite46 ตรวจโค้ดสุดท้ายซ้ำแล้ว จำนวนเหล่านี้มี tests ซ้ำกันระหว่างชุด จึงไม่บวกรวมเป็นจำนวน tests ทั้งหมด Full Playwright เดิมไม่ได้รันซ้ำในงานนี้

Local E2E สร้าง Pipeline ผ่าน Settings, ตรวจ readiness, อัปโหลดภาพสังเคราะห์780×250, สร้าง manual ROI, เลือก External ร่วมกับ Pipeline เดิมที่จำลอง CDGS, รับ Job202, refresh, อ่านผลที่ persist, บันทึก GT, ประเมิน CER/WER/Exact Match, เปิด History และ Evaluation ZIP ได้ มี Job submission เดียว

ข้อความที่วาดและผล OpenThai จริงตรงกันในตัวอย่างนี้

```text
ทดสอบภาษาไทย 123
OpenThai OCR 2026
```

CER0/WER0/Exact Match=true ตรงกับ reference ที่กำหนดไว้ก่อน inference สำหรับ fixture นี้ ส่วน CDGS ใน regression/E2E ใช้ MockTransport ตาม test infrastructure เดิม และ standalone unit tests ใช้ reader doubles

## Contract และทรัพยากร

โมเดล revision `39fa41bdd49f067ba41b1d9de79c06ab506d67d4` ใช้ ONNX Runtime, `LineOCR(..., threads=1)`, รักษา text/line reading order และ polygon ในพิกัดภาพต้นฉบับ Confidence รายบรรทัดมาจาก CTC ส่วน aggregate confidence คืน null ภาพว่างคืน textว่าง/linesว่าง

Docker image ที่ตรวจ `sha256:a9ffd7aa04fef95b8b007523cf8ead2472eae486a6959e6338e58cf5aefa6abb`

| ค่าที่วัด | ผล |
| --- | --- |
| Container limit | 1,610,612,736 bytes, 1 CPU, no swap |
| Kernel memory.peak | 435,372,032 bytes รวม file cache |
| Process VmHWM | 249,732 KiB |
| Cold start ถึง readiness | ประมาณ1.06วินาที |
| Blank inference | 103.64 ms |
| Thai/English inference | 107.23 ms, 2 lines |
| memory.events max/oom/oom_kill | 0/0/0 |
| Restart | readiness200, inference200, ข้อความตรงเดิม |

การวัดนี้เป็น smoke workload ขนาดเล็กหนึ่ง process ขนาด RAM สำหรับ dense pages, ภาพหมุน, workload ต่อเนื่องและ concurrency บน CDGS ต้องวัดเพิ่มเติม เครื่อง Windows รอบแรกวัด PID ของ venv launcher จึงไม่นำค่าหน่วยความจำรอบนั้นมาใช้สรุป ผลหลักใช้ Linux cgroup และ `/proc/1/status` จาก container

## การแก้ปัญหาที่พบระหว่างตรวจ

- Manifest ต้นทางมี README checksum เก่า ตรวจ runtime/weights/config กับ manifest ต้นทางและตรึง checksum README ที่ตรวจแยกไว้ การเริ่ม service ตรวจ committed manifest ทุกไฟล์
- SSRF tests พบ Python `is_global` เพียงอย่างเดียวยังยอมรับ multicast จึงบล็อก multicast/reserved/IPv6 transition/NAT64/site-local เพิ่ม และทดสอบซ้ำ
- Deadline test พบ BaseHTTPMiddleware รอ native thread ก่อนส่ง timeout จึงเปลี่ยนเป็น ASGI middleware และคง slot จน native call จบ กรณี timeout→busy→พร้อมรับคำขอใหม่ผ่าน
- PostgreSQL container local ยังหยุดอยู่ ทำให้รอบแรกมี2environment failures เปิด containerทดสอบเดิมแล้ว full Backend ผ่าน729ข้อ
- Comparison fixture เดิมยังคาดหวัง Deep detail แบบ inline และไม่มี upload-config/error-summary รวมหลาย Field ปรับ fixture/assertions ให้ตรง dialog และ contract ปัจจุบัน โดยยังตรวจข้อความผิด/ขาด, highlight, scroll, metrics, GT edits และ failure paths
- Selector test ใหม่ชน Next route announcer ปรับให้เจาะ error banner ของฟอร์ม
- รอบยืนยัน E2E เคยชน local server ที่ teardown ไม่สำเร็จ และ build ใช้ API URL คนละพอร์ต แก้ harness ให้ตรวจพอร์ต/ตรวจ process, แยกชื่อ log และ build ด้วย URL localhost ที่ตรงกัน แล้วรัน real E2E ผ่านซ้ำ

## การรันซ้ำแบบแยกจาก Production

Standalone ใช้คำสั่งใน `api/openthai2_ocr_text/docs/LOCAL_TESTING.md` ฝั่ง OCRLab ตั้ง `EXTERNAL_OCR_DEVELOPMENT=true` และทะเบียน loopback provider ตามคู่มือ security ใช้ฐานข้อมูล PostgreSQL local ชื่อลงท้าย `_test` และ `TEST_DATABASE_URL` สำหรับ `tests.e2e_app` ซึ่งจำลองเฉพาะ CDGS

```sh
# Terminal1, service directory
python -m uvicorn app.main:app --host 127.0.0.1 --port 8091
# Terminal2, backend directory, with explicit local TEST_DATABASE_URL and provider env
python -m uvicorn tests.e2e_app:app --host 127.0.0.1 --port 8100
# Terminal3, frontend directory
# Set NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8100 before build
npm run build
npm run start -- --hostname 127.0.0.1 --port 3100
# Terminal4, frontend directory
# Set E2E_API_URL=http://127.0.0.1:8100 and E2E_BASE_URL=http://127.0.0.1:3100
npx playwright test tests/external-pipelines.spec.ts tests/dynamic-pipelines.spec.ts tests/ocr-jobs.spec.ts tests/global-comparison.spec.ts
npx playwright test --config=playwright.external.config.ts
```

เลือก endpoint/port และ synthetic private key ให้ตรงกันทั้งทะเบียนกับ service การทดสอบจริงใช้ synthetic PNG ที่ commit ใน `frontend/tests/fixtures/openthai-thai-english.png`

## ข้อจำกัดและส่งมอบ

- คง Draft PR เพื่อ review การปล่อย CDGS ต้องให้เจ้าของโครงสร้างพื้นฐานกำหนด TLS route, capacity, permissions, credentials และ ingress controls
- Provider HTTPS deployment จริงและ shared-server capacity ยังรอ infrastructure owner งานนี้ตรวจ localhost และ container local
- Backend ใช้ httpx/httpcore รุ่นที่ตรึงไว้สำหรับ DNS-pinned transport การอัปเกรดต้องตรวจ transport regression
- HTTP deadline คืน504และรักษา native slot ระหว่างที่โมเดลยังทำงาน หาก native callค้างถาวรต้องให้ supervisor restart process
- Geometry และ output ใช้ขอบเขตที่ตรวจได้ API จำกัด output, OCRLab จำกัด lines128ตามการป้องกันเดิม ผลเกินขอบเขตจะเป็น per-pipeline failure
- Public shared workspace และ uploads แบบ ephemeral เป็นคุณสมบัติ/ความเสี่ยงเดิม REQ-12 อยู่นอกขอบเขต

เอกสาร deployment อยู่ใน `api/openthai2_ocr_text/docs/DEPLOYMENT.md` หลักฐาน raw เก็บใน ignored `.runtime/openthai-validation/` งานนี้ไม่มี Production data operation หรือ CDGS deployment
