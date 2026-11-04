# Isolated OCR concurrency diagnostics

## สถานะ

Railway staging **ยังไม่ได้สร้าง**: ผู้ใช้อนุมัติ temporary staging usage แล้ว แต่ Railway ปฏิเสธด้วย Free plan resource quota และยังไม่ได้อนุมัติการ upgrade subscription ไม่มี staging deployment ID ดูผล baseline ใน [report-th.md](report-th.md), [results.json](results.json) และผลแก้ไขใน [report-final-th.md](report-final-th.md)

ชุด local ถูกหยุดหลังเก็บหลักฐานแล้ว โดยคง volumes และ evidence ไว้ ใช้คำสั่ง up ด้านล่างเมื่อต้องการเปิดอีกครั้ง

ชุดทดสอบใช้ **Mock Gateway เท่านั้น** ไม่มี production API key/DB URL และไม่ส่ง load ไป CDGS จริง จึงไม่สามารถยืนยันสาเหตุ HTTP422 หรือ model-worker concurrency ของ CDGS

## สิ่งที่เตรียม

- Source archive จาก production commit `67df434dabed0eeb70a38009fc33fde0e12eba41` โดยไม่ checkout/reset หรือเปลี่ยน app files ใน workspace
- Docker image สร้างด้วย Dockerfile/requirements-runtime-lock.txt จาก commit นั้น ไม่ใช่การ clone runtime dependency versions จาก Railway
- Backend: 1 CPU / 512,000,000 bytes memory, 1 process, restart=no
- PostgreSQL 17: database ใหม่ ไม่มีข้อมูลผู้ใช้; volume ใหม่เฉพาะ Docker Compose project นี้
- Storage volume ใหม่เฉพาะ local ไม่มี mount หรือ reference ไป production uploads
- Backend อยู่เฉพาะ Docker internal network ที่ไม่มี external egress; mock/proxy มี local ingress, ports bind `127.0.0.1` เท่านั้น
- Nginx proxy ใช้เป็น local proxy stand-in ไม่ใช่ Railway edge และไม่จำลอง sleep/restart policy ของ Railway
- Observer เป็น launcher ภายนอก app files: sample RSS, cgroup counters และ CPU ทุก 50 ms, JSON decoding boundaries, Gateway requests; เพิ่ม counters แยก HTTP/pipeline/field ใน supplemental probes

## วิธีรันบน Windows

ต้องมี Docker Desktop Linux engine และ Python environment ของ backend เดิม รันจาก repository root:

```powershell
backend/.venv/Scripts/python.exe postman/staging/prepare-local.py
docker compose --env-file .runtime/staging-diagnostics/compose.env -f postman/staging/local-compose.yml up -d --wait
backend/.venv/Scripts/python.exe postman/staging/concurrency-test.py
```

prepare-local สร้าง private local DB password ใน ignored `.runtime/staging-diagnostics/compose.env` และเก็บค่าเดิมเมื่อรันซ้ำ ไม่อ่าน `.env` production ไม่พิมพ์ credentials

การรัน matrix จะเพิ่ม **synthetic local records ใหม่** และเขียน results.json ทับ ต้องเก็บผลเดิมก่อนรันใหม่ ทุก stage มี 1 trial ยกเว้น HTTP concurrency=2 ซึ่ง dispatch สอง runs พร้อมกัน ไม่มี loop ไม่จำกัด ไม่เพิ่ม stage หลังพบ 5xx/connection/pipeline error/process exit/OOM

หลัง intentional local restart ต้องรอ health ready ก่อนเริ่ม test ไม่ตีความ setup 502 ช่วง backend ยังไม่ฟัง port ว่าเป็น OCR-load failure ในรอบนี้มี setup health502 หนึ่งครั้งหลังเพิ่ม observer หยุดก่อนส่ง OCR แล้วตรวจ readiness200 จึงค่อยทำ compact D/F probes ที่จำกัดไว้

## Profiles และ dataset

- `compact`: leaf contract และ results ขนาดเล็ก
- `sized`: รูปแบบเดียวกันและเพิ่ม numeric JSON array จำลอง ~3.33 MB ต่อ REC input ขนาดอิง response bytes ที่เคยวัด แต่ **ชนิด/ตำแหน่ง payload ไม่ได้ capture จาก CDGS** และไม่ใช่ weights/model inference จริง
- Small 1000x240, Medium 2000x1200, Large 4000x2400; SHA-256/ROI คงเดิมเมื่อเทียบสอง profiles
- 4 synthetic pipelines ใช้ query aliases baseline, REC5 thai_ft_v3, DET6 thai_ft_v2 + REC5 thai_ft_v4, REC6 thai_ft_v1 ส่วน REC5 thai_ft_v6 ตรวจ simulator contract ใน gateway-only baseline
- ไม่ inject422เพื่อสร้างผลล้มเหลวปลอม: ค่า422=0ใน mock ไม่ได้พิสูจน์ว่า CDGSไม่มี422

## Artifacts / การหยุด

`test-matrix.json` ระบุ counts/limits; `results.json` เก็บ stage timings, gateway events, batch counts, memory/CPU, container states และ supplemental actual-task counters

หลักฐานละเอียดอยู่ ignored `.runtime/staging-diagnostics/`: source.tar, source/backend, evidence/process.jsonl, production-audit.json, newman-local.json, targeted-results.json และ targeted-startup-race.json ไม่มี request bodies, uploaded documents จริง, API keys หรือ Authorization headers ใน reports

หยุดเฉพาะชุด local โดยเก็บ volumes/evidence:

```powershell
docker compose --env-file .runtime/staging-diagnostics/compose.env -f postman/staging/local-compose.yml stop
```

ห้ามใช้ `down -v` กับ environment อื่นโดยพลการ ไม่มีคำสั่งจัดการ production ใน scripts ชุดนี้

## Recovery candidate comparison

เก็บ baseline results.json ไว้ก่อน และหยุด baseline containers เพื่อคืน localhost ports จากนั้นรัน candidate ด้วย DB/storage คนละ Compose project:

```powershell
docker build -t ocrlab-recovery:candidate backend
New-Item -ItemType Directory -Force .runtime/recovery/evidence
docker compose -p ocrlab-recovery-after --env-file .runtime/staging-diagnostics/compose.env -f postman/staging/local-compose.yml -f postman/staging/recovery-compose.yml up -d --wait
backend/.venv/Scripts/python.exe postman/staging/concurrency-test.py --after
```

โหมด --after บันทึก results-final.json และ source tree hash; ไม่เขียนทับ baseline results.json ควรเก็บ report เดิมก่อนรันทุกครั้ง Mock/source sizes และ matrix ใช้ชุดเดียวกัน ดู [ผลแก้ไข](report-final-th.md) สำหรับ tradeoff เรื่องจำนวน Gateway calls/latency และ residual risk

## Cloud / real CDGS gate ที่ยังค้าง

การอนุมัติ temporary usage มีแล้ว แต่ต้องแก้ Free plan provisioning quota ก่อน โดยไม่ upgrade subscription อัตโนมัติ อัตรา CPU/RAM อยู่ที่ [Railway pricing](https://docs.railway.com/pricing/plans) เมื่อสร้างได้ให้ใช้ database/storage ใหม่ ห้ามอ้างอิง production DATABASE_URL หรือ clone ข้อมูลผู้ใช้

ก่อน concurrent test กับ CDGS จริง ต้องยืนยัน credential/load-test permission และขอบเขต shared Gateway ก่อน การมี key ที่เรียก single request ได้ไม่ใช่หลักฐานสิทธิ์ทำ load test
