# CDGS diagnostics — Postman / Newman

ใช้ตรวจปัญหา HTTP 422/502 แบบจำกัดจำนวนคำขอ ไม่เปลี่ยน production code, model config หรือ environment และไม่มี secret ในไฟล์ชุดนี้

## Import ใน Postman

1. Import `cdgs-diagnostics.postman_collection.json` (Collection v2.1) และ `cdgs-diagnostics.postman_environment.json` แล้วเลือก environment นี้
2. ใส่ Gateway key ใน local/private value ของ `gateway_api_key` เท่านั้น ห้ามแชร์หรือ export environment ที่เติม key แล้ว
3. ปิด Automatically follow redirects เลือกไฟล์ `synthetic.png` ที่ field `images`/`file` หาก Postman ยัง resolve relative file ไม่ได้ ภาพนี้สร้างขึ้นสำหรับทดสอบ ไม่มีข้อมูลเอกสารจริง
4. รัน folder `01 Read-only preflight` แล้ว `02 Baseline sequential` ครั้งเดียวก่อน

Gateway URL ต้องเป็น `https://websolution.cdgs.co.th/paddle/api/v1` ใช้ Bearer เฉพาะ Gateway requests ส่วน Backend requests ไม่รับ Gateway key Collection ตรวจ host/prefix ก่อนส่งและไม่ใช้ Integrated/Custom OCR endpoints

Folder 03 ปิดการเขียนโดย default (`allow_synthetic_writes=false`) หากเปิดใช้จะ **เพิ่ม document, test case, layout และ OCR result ใหม่ใน History** ไม่ลบข้อมูลทดสอบอัตโนมัติ ไม่แก้ข้อมูลเดิม รัน 1 pipeline / 1 field และกำหนด manual GT ก่อน OCR เพื่อไม่ให้เกิด system GT prefill เพิ่ม Pipeline baseline ที่ enabled จะถูกเลือกจาก catalog; หากไม่มี baseline ที่ตรงต้องหยุด ไม่เปลี่ยน config เพื่อให้ทดสอบผ่าน

## Newman แบบไม่ส่ง key ผ่าน CLI หรือบันทึกลง report

จาก repository root บน Windows ใช้ backend virtualenv เดิม (มี python-dotenv):

```powershell
npm.cmd install --prefix .runtime/cdgs-newman-tools --no-save --package-lock=false newman
node postman/run-diagnostics.cjs baseline
```

Runner อ่านเฉพาะ Gateway key จาก `.env` เข้า memory และเรียก Newman programmatically โดยไม่ใช้ raw JSON reporter ซึ่งอาจแนบ headers/credentials มาด้วย ตำแหน่งไฟล์ภาพถูก resolve แบบ absolute ใน memory

โหมดที่มี:

| Command | จำนวนสูงสุด | ผลข้างเคียง |
|---|---:|---|
| `node postman/run-diagnostics.cjs read` | 3 GET | อ่าน health/catalog |
| `node postman/run-diagnostics.cjs baseline` | 3 GET + 7 Gateway POST | ภาพสังเคราะห์ ภาพละ 1 batch |
| `node postman/run-diagnostics.cjs single` | 3 Gateway POST | Test A: REC V5 thai_ft_v6 sequential 3 trials |
| `node postman/run-diagnostics.cjs backend` | 8 HTTP calls | เพิ่ม synthetic case ใหม่และรัน baseline 1 pipeline / 1 field |

อย่ารันซ้ำต่อเนื่อง โหมด backend ไม่ใช่ read-only ต้องอยู่ในขอบเขต smoke ที่ได้รับอนุญาตแล้ว หากเกิด 5xx/429/connection error runner จะ abort; โหมด backend หยุดเมื่อพบ HTTP error ทุกชนิด การ assertion fail รายงานแยกจาก HTTP success โดยไม่แสดง OCR/GT เต็ม

Reports อยู่ใน `.runtime/cdgs-newman/newman-<mode>.json` เป็น sanitized Newman evidence มี start/end, status, latency, response byte size, request IDs, model selection, assertions และ error allowlist เท่านั้น ไม่เก็บ raw response หรือ Newman summary ทั้งก้อน ไฟล์ชื่อเดิมจะถูกเขียนทับเมื่อรันโหมดเดิมอีกครั้ง ควรเก็บหลักฐานเดิมก่อนรันรอบใหม่

## Concurrency — staging เท่านั้น

Newman iteration ไม่ใช่ concurrent execution Test B และ C ใช้ `run-concurrency.py` ซึ่ง dispatch ด้วย `asyncio.gather` พร้อม start/end ของแต่ละคำขอ:

- B: concurrent 2, สูงสุด 3 trials = 6 OCR calls
- C: concurrent 4, สูงสุด 2 trials = 8 OCR calls

ต้องมี staging แยกที่ยืนยัน configuration/resources แล้ว เตรียม synthetic global case ชื่อไฟล์ขึ้นต้น `CDGS_DIAGNOSTIC_`, 1 field, manual GT และ baseline pipeline ให้พร้อม กำหนด environment เฉพาะ diagnostic runner:

```powershell
$env:STAGING_BACKEND_BASE_URL="https://YOUR_ISOLATED_STAGING_HOST"
$env:STAGING_SYNTHETIC_CASE_ID="YOUR_SYNTHETIC_CASE_UUID"
$env:STAGING_PIPELINE_ID="YOUR_STAGING_PIPELINE_ID"
$env:ALLOW_STAGING_CONCURRENCY="true"
backend/.venv/Scripts/python.exe postman/run-concurrency.py --level B
# ตรวจผลก่อน แล้วจึงรัน --level C หาก staging ยังปกติ
```

ตัวแปรเหล่านี้ไม่ใช่ application environment ใหม่ และไม่ต้องตั้งบน Railway production Script ปฏิเสธ production/CDGS hosts และตรวจ case ก่อนส่ง POST เมื่อมี 5xx/429/connection error จะไม่เริ่ม trial ถัดไป ส่วนคำขอที่ส่งพร้อมกันไปแล้วอาจยังทำงานอยู่บน server ห้ามเข้าใจว่า client สามารถยกเลิกงาน upstream ได้แน่นอน Backend อาจ serialize งานด้วย OCR lock จึงต้องใช้ server logs ยืนยัน actual inference concurrency เพิ่มเติม

รอบนี้ **ยังไม่รัน B/C** เพราะ Railway inventory ที่เข้าถึงมีเพียง production environment ห้ามนำ production มาแทน staging

## ผลรอบ 4 พฤศจิกายน 2569

ดู [ผลสรุป](reports/results-2026-11-04.md) และ [sanitized Newman summary](reports/newman-summary.json) การทดสอบไม่ทำให้ 422/502 เกิดซ้ำ จึงยังไม่ยืนยันสาเหตุเดิมจาก single-image success เพียงอย่างเดียว
