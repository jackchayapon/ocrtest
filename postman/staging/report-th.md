# OCR concurrency diagnostics — 4 พฤศจิกายน 2569

> รายงานนี้เป็น baseline ก่อนแก้ไขและก่อนอนุมัติ temporary cloud usage ภายหลังได้รับอนุมัติแล้วแต่ Railway ปฏิเสธเพราะ Free plan provisioning quota ดูสถานะล่าสุดใน [report-final-th.md](report-final-th.md) โดยไม่เปลี่ยนค่าผลวัดเดิมด้านล่าง

## สถานะการส่งมอบ

**LOCAL ISOLATED TESTS COMPLETE — RAILWAY STAGING PENDING COST APPROVAL — REAL CDGS CONCURRENCY NOT VERIFIED**

ยังไม่ได้สร้าง cloud resource ที่มีค่าใช้จ่าย เนื่องจากคำถามอนุมัติค่าใช้จ่ายยังไม่มีคำตอบ และยังไม่ยืนยันสิทธิ์ low-load concurrent test บน shared CDGS จึงใช้ local isolated Docker + Mock Gateway ตามทางเลือกในงาน ผลด้าน memory เป็นผลวัดจริงของ application code ที่รับ synthetic response ไม่ใช่ผล inference ของ CDGS

- Local staging URL ที่ใช้ทดสอบ: http://127.0.0.1:18080 — หยุดชุด local หลังเก็บหลักฐานแล้ว ไม่ได้เปิดให้บริการค้างไว้
- Mock diagnostics: http://127.0.0.1:18081/diagnostics
- Railway staging URL / Deployment ID: **ไม่มี — ยังไม่ได้สร้าง**
- Production deployment ที่อ่านได้: 432a98fb-8c9e-4fa9-bdb3-2e6e4cbf66cd
- Production deployed SHA และ remote GitHub main: 67df434dabed0eeb70a38009fc33fde0e12eba41
- Local application source ใช้ git archive ของ SHA เดียวกัน ไม่มี app source edits; instrumentation เป็น local launcher ภายนอก

## Production read-only audit

ตรวจ provider configuration/deployment, metrics และ remote main ใหม่ ไม่เปลี่ยน production variables ไม่ปลุกด้วย inference หรือ restart/deploy service

- Region asia-southeast1-eqsg3a, 1 replica, Sleep Application=true
- CPU limit ที่ metrics แสดง=1; Memory limit=0.512 GB
- Railpack, root /backend, watch /backend/**, GitHub source main
- Config ที่เครื่องมือคืนมาไม่มี explicit start command/healthcheck/restart-policy override จึงไม่อ้างว่าได้ตรวจ default restart policy/exit settings ครบ
- ไม่มี attached volumes; ไม่เปลี่ยน storage หรือ production data
- OAuth คืน variable names แต่ไม่คืน values ตรวจยืนยันได้ว่า names อยู่ใน service ส่วนสถานะ non-empty/sealed ของค่าที่ถูกซ่อนยังไม่ยืนยัน ไม่มีการพิมพ์ key/DB URL
- Metrics audit 4h: sampled memory max 0.386310144 GB, current 0.1605632 GB; ไม่ใช่ memory ณ วินาทีที่ historical502

## Isolation / parity

Backend จำกัด 1 CPU / **512,000,000 bytes**, 1 process; PostgreSQL17 database ใหม่; uploads volume ใหม่ ไม่มี production DB URL/key และไม่ clone records/documents ผู้ใช้ Backend อยู่เฉพาะ Docker internal network; ingress เฉพาะ proxy/mock บน localhost

Local migration=0011_gt_prefill; หลัง main matrix และ supplemental probes มี synthetic documents21 / cases21 / pipeline_runs42 เท่านั้น ไม่มี SQL mutation บน production

Runtime ไม่เหมือน Railway ทุกด้าน: Dockerfile/lockfile จาก SHA เดียวกัน แต่ production ใช้ Railpack dependency resolution ซึ่งไม่ได้ตรวจ installed packages ทีละตัว; Nginx เป็น proxy stand-in; PostgreSQL local ต่างจาก Neon; ไม่จำลอง production sleep policy, historical load, hardware และ CDGS worker state

## สิ่งที่นับแยกกัน

1. Concurrent HTTP runs: client dispatch /run พร้อมกัน 1 หรือ2
2. Pipeline tasks: adapter tasks ของแต่ละ pipeline ภายในแต่ละ field
3. Field tasks: GlobalLayoutService ใช้ gather สำหรับ fields ภายใน bounded group
4. Gateway batch calls: BatchGateway รวมตาม URL + exact query จึงไม่เท่ากับ pipeline task count
5. Images per Gateway batch: ขนาดไฟล์ list ของแต่ละ call; IMAGE_BATCH_SIZE=30 เป็น cap ต่อ batch/group ไม่ใช่30 HTTP requests พร้อมกัน

Source /run ใช้ app.state.ocr_lock ต่อ process ดังนั้นสอง incoming HTTP requests อาจรอคิว แม้ field/pipeline work ภายใน run จะขนานกันได้

## Main matrix — 1 trial ต่อ stage/profile

Peak Memory เป็น **sampled cgroup MB (decimal)**; P95 nearest-rank มี n=1 หรือ2 จึงเท่ากับค่าสูงสุดของ sample เล็ก ไม่ใช่ capacity percentile ที่เชื่อถือได้ใน production

| Profile / Stage | Pipelines | Fields | HTTP concurrency | Success | 422 | 502 | Peak Memory MB | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| compact A | 1 | 1 | 1 | 1/1 | 0 | 0 | 145.5 | 396.85 |
| compact B | 2 | 1 | 1 | 1/1 | 0 | 0 | 147.2 | 373.14 |
| compact C | 4 | 1 | 1 | 1/1 | 0 | 0 | 151.9 | 424.57 |
| compact D | 2 | 2 | 1 | 1/1 | 0 | 0 | 186.5 | 530.36 |
| compact E | 4 | 4 | 1 | 1/1 | 0 | 0 | 360.1 | 1670.48 |
| compact F | 1 | 1 | 2 | 2/2 | 0 | 0 | 150.5 | 709.51 |
| compact G | 2 | 2 | 2 | 2/2 | 0 | 0 | 187.5 | 1029.64 |
| sized A | 1 | 1 | 1 | 1/1 | 0 | 0 | 198.4 | 456.12 |
| sized B | 2 | 1 | 1 | 1/1 | 0 | 0 | 209.4 | 596.33 |
| sized C | 4 | 1 | 1 | 1/1 | 0 | 0 | 223.8 | 836.11 |
| sized D | 2 | 2 | 1 | 1/1 | 0 | 0 | 262.1 | 1100.96 |
| sized E | 4 | 4 | 1 | 1/1 | 0 | 0 | **511.9** | **4994.14** |
| sized F | 1 | 1 | 2 | 2/2 | 0 | 0 | 140.6 | 926.05 |
| sized G | 2 | 2 | 2 | 2/2 | 0 | 0 | 190.5 | 2088.13 |

รวม **18 OCR HTTP runs**, **60 Gateway batch calls** ภายใน main matrix ผล run/field success ทั้งหมด ไม่มี injected422 ค่า422=0จึงไม่ใช่การทดสอบความเสถียรของ CDGS เนื่องจาก mock ไม่มี model worker จริง

Gateway-only simulator contract checks 7 requests แยกจาก main matrix; supplemental probes D/F ตรวจเพิ่ม3 OCR runs เพื่อยืนยัน task counters ไม่ทำ full matrix ซ้ำ Newman local functional validation 3 GET /6 assertions ผ่าน แยกจาก Newman real Gateway evidence รอบก่อน

## Actual task / batch observations

Supplemental compact probes หลังเพิ่ม observer counters:

| Probe | Max HTTP runs active | Max field tasks | Max pipeline tasks | Max Gateway calls inflight |
|---|---:|---:|---:|---:|
| D: 2 pipelines x2 fields | 1 | 2 | 4 | 2 |
| F: 2 HTTP runs, 1 pipeline x1 field | 2 | 1 | 1 | 1 |

ยืนยันว่า OCR lock serialize สอง incoming requests ใน process นี้ และการมี4 pipeline tasks ไม่ได้แปลว่ามี4 leaf HTTP calls เสมอ ไม่ได้ instrument task counters ครบทุก stage ใน main matrix; max Gateway inflight วัดได้ทุก stage และสูงสุด4

Stage E แต่ละ profile มี6 batch calls: DET batches4และ12 images; REC batches4 images x4 calls ไม่มี batch ถึง cap30 ไม่ควรขยายผลว่า30ภาพผ่านแล้ว ทุกคำขอส่ง version/model ตามเลือก ไม่พบ query ปะปน

## Resource / process evidence

- Main matrix ทั้ง14 stage/profile ใช้ container start เดียวกัน host PID907 / observer namespace PID1, RestartCount0, Running=true, OOMKilled=false ตลอด workload ไม่เกิด kill/restart
- sized E ส่ง decoded synthetic responses รวม53.29 MB ผ่าน6 calls; max cgroup current511,897,600 bytes จาก limit512,000,000; memory.events max เพิ่มเป็น202 แต่ oom=0 / oom_kill=0
- sized E sampled RSS540.3 MB เป็น accounting คนละแบบกับ cgroup current จึงไม่ใช้ RSS เทียบ limit โดยตรง
- JSON decode boundaries ใน E พบ RSS เพิ่มประมาณ30–40 MB ต่อการ decode body ~13.32 MB; ไม่ได้วัด exclusive allocation ของ safe_response/deepcopy/normalization แยกทั้งหมด
- CPU time sampled ของ E: compact1.329 CPU-seconds /wall1.706s; sized4.556 CPU-seconds /wall5.033s
- หลัง E memory ลดลงใน F ไม่มีหลักฐานว่าทุก allocation เป็น permanent leak; ไม่ได้ทดสอบ long-running leak
- Input ใช้ multipart PNG ไม่มี input Base64 path; mock ไม่จำลอง upstream Base64 จึงยังไม่วัดผลของ Base64 decoding จริง
- เก็บ GC generation2 events และ RSS/cgroup ทุก50ms; การ drop memory ไม่ได้พิสูจน์ว่า GC เป็นสาเหตุเดียว

### Supplemental startup 502

หลังจบ main matrix มี intentional **local-only** backend restart เพื่อเพิ่ม task observers แล้ว health request ที่ส่งก่อนพร้อมได้502 runnerหยุดก่อนส่ง OCR เก็บ targeted-startup-race.json ตรวจ readiness200ก่อนจึงทำ compact D/F เพิ่ม ไม่มีการเพิ่ม load ขณะ unhealthy เหตุการณ์นี้เป็น setup/readiness failure ที่รู้บริบท ไม่ใช่การ reproduce historical production OCR502 และไม่มี production restart

## Root cause status

| ประเด็น | Status | ข้อสรุปที่หลักฐานรองรับ |
|---|---|---|
| Numeric response ขนาดใหญ่สร้าง memory/CPU pressure ใน workload จำลอง | **CONFIRMED เฉพาะ local mock** | E sized เข้าใกล้ memory cap, max counter202, decode allocation และ runtimeสูงกว่า compact |
| Production502 เดิมเกิดจาก OOM | **UNCONFIRMED** | ยังไม่มี historical exit/signal/OOM event; localไม่เกิดOOM kill |
| Response memory pressure เป็นปัจจัยเสี่ยงของ production | **LIKELY** | ขนาด RECจริงเคยวัด~3.33MB/ภาพ และ localแสดงpressure แต่ชนิดpayload/ฐานmemory/platformต่างกัน |
| Production502 เดิมเป็น proxy connection closure และตามด้วยprocess start | **CONFIRMED เฉพาะเหตุการณ์ที่บันทึก** | ยังไม่ทราบเหตุที่process/connectionสิ้นสุด ไม่อนุมานว่าเป็นOOM |
| Concurrent HTTP=2 ทำให้สอง OCR runs executeพร้อมกันในprocessเดียว | **RULED OUT ใน local single-process probes นี้** | activeHTTP2แต่field/pipeline/Gatewayสูงสุด1ในF เพราะlock; ไม่ครอบคลุมหลายreplica/process |
| Concurrency/model loading/inputเป็นเหตุCDGS422เดิม | **UNCONFIRMED** | ไม่มี real concurrent CDGS calls/internal errors ไม่มีสิทธิ์โหลดที่ยืนยัน |
| Weight aliases ที่ทดสอบ single ก่อนหน้านี้ unsupportedถาวร | **UNCONFIRMED/ไม่สนับสนุนโดยผลเดิม** | real single testsเคยผ่าน ไม่เท่ากับproductionworkerทุกตัวพร้อมเสมอ |

## Proposed fixes — ยังไม่ apply

1. จำกัด in-flight processing ตาม decoded response memory budget และจำนวน field/pipeline tasks ภายในหนึ่ง run; lockระดับHTTPอย่างเดียวไม่จำกัด internal concurrency
2. ตรวจและตัด unused heavy transport fields ก่อน BatchGateway deepcopy/result normalization โดยรักษา results ordering, count, model_selection, request IDs และ metadata; sourceปัจจุบันdeepcopy templateทั้งpayloadต่อowner การแบ่งเฉพาะresultsไม่ได้แบ่งทุกrawfield
3. ทดลองลด field group/batch budget ใน staging เทียบ memory/latencyด้วย inputเดิม ก่อนตัดสินค่าใหม่ ไม่อ้างว่า cap30คือconcurrentHTTP30
4. เพิ่ม safe upstream diagnostics และจำแนก UPSTREAM_MODEL_ERROR แยกจาก schema validation; ไม่ retry422 หรือสลับ weights เพื่อให้ดูผ่าน
5. เก็บ cgroup OOM/exit signal/process lifecycle ที่ช่วงเหตุการณ์จริง และ per-request/phase memory; sampledRailwaymetrics60sอย่างเดียวไม่พอ

ไม่มีการแก้ production application หรือ config ในรอบนี้ ไม่มี commit/push/merge/deploy และไม่แก้ weights หรือเพิ่ม retry

## Remaining unknowns / cloud gate

- ต้องอนุมัติค่าใช้จ่ายก่อนสร้าง Railway staging พร้อม DB/storage ใหม่ ไม่ใช้ production DB
- ต้องยืนยันสิทธิ์ concurrent tests บน CDGS shared gateway หรือมี isolated model deployment ก่อนทดสอบจริง
- ยังไม่ทราบ production checkpoint/worker state ณ เวลาที่422, exact failed leaf inputs/batch sizes และ process exit reasonของ502
- ยังไม่ยืนยัน resource/runtime parity กับ Railwayทุกด้าน หรือพฤติกรรมระดับ30images, หลายreplica และ sustained load
- Local mockที่ทำงานสำเร็จไม่สามารถใช้ประกาศว่า production issueได้รับการแก้แล้ว

ดู results.json สำหรับ timestamps, synthetic IDs, request IDs, batch counts, CPU, memory และ Docker state ของแต่ละ stage; หลักฐาน samplingละเอียดอยู่ .runtime/staging-diagnostics/evidence/process.jsonl ทั้งหมดไม่มี secrets หรือเอกสารผู้ใช้จริง

## Final validation / cleanup

JSON, Python syntax และ Compose config ผ่าน ตรวจ aggregate digest ของ app source ใน container ตรงกับ source archive ของ production SHA; secret scan ไม่พบค่าจาก private .env และไม่พบ trailing whitespace ในไฟล์ใหม่ ไม่มี tracked app diff มีเฉพาะ untracked postman/ ตามงานก่อนหน้าและงานนี้

หลังทดสอบหยุดเฉพาะ local Compose project นี้ด้วย stop เก็บ volumes/evidence ไว้ครบ Backend หยุดปกติ ExitCode0 / OOMKilled=false ไม่ใช่ crash ระหว่าง test ไม่มีการหยุดหรือ restart Railway production
