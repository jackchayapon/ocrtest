# OCRLab memory reliability — local pre-release evidence

ตรวจ 8–9 พฤศจิกายน 2569 จาก baseline `607af992867dd33425597d22efb5d7f489fbadc7` บน branch `perf/ocr-memory-reliability`; code candidate `f8c7949ba5e11e162e59b340b37d0dc607a38b54`. ผลสำหรับ **512 MB: NO-GO** ไม่มีการปรับ Production resources

## สิ่งที่แก้

- `model_gateway.py`: ตรวจ Content-Length ที่เชื่อถือขนาด decoded ได้ก่อนอ่าน; อ่านเป็นช่วง 64 KiB และตรวจ decoded byte limit ก่อนเขียน; RAM spool 1 MiB ต่อ response แล้วใช้ OS-private temporary file ซึ่งปิดทุก exit path ก่อนคืนผล ไม่เขียนใน uploads และไม่ log ชื่อ/เนื้อหา
- `gateway_response.py`: ใช้ ijson 3.6.0 ตรวจ JSON ทั้งหมด แต่ไม่สร้าง Python object tree ของ top-level transport archives และ embedded image tensors ที่ถูก redact อยู่แล้ว เก็บ data/meta/error และ sanitize strings ระหว่าง parse ไม่มี tree copy รอบที่สอง
- `image_service.py`: transpose EXIF ใน image ที่ decode อยู่แล้ว; ไม่ทำสำเนา RGB ที่ไม่จำเป็น; เปิด RGB โดย load pixels ก่อนปิด input buffer; crop RGB เฉพาะ ROI แทนแปลง source ทั้งหน้าเป็น NumPy ล้าง crop metadata ให้ตรงกับ Image.fromarray เดิม
- ไม่เปลี่ยน model routes/params, OCR predictions, metrics/GT, field/job/checkpoint IDs, default concurrency, image limits หรือ batch limits ไม่มี migration และไม่มี environment variable ใหม่
- JSON parser ต้องเป็น JSON ที่สมบูรณ์; NaN/Infinity literals ซึ่งไม่ใช่ JSON มาตรฐานถูกปฏิเสธเป็น INVALID_RESPONSE ส่วน finite numbers, arbitrary-size integers และ exponent overflow ที่ sanitize เป็น null มี regression tests

## วิธีวัด

Docker local เท่านั้น: backend memory.max **512,000,000 bytes**, **1 CPU**, fields group 8, pipeline tasks 4, Gateway batch default **4** (protocol/adapter line grouping cap 30), response limit 64 MiB ค่าเดิมทั้งหมด ใช้ mock ที่แยก container และ synthetic image ไม่มี CDGS/Production credentials

ภาพ 4000×3200 (12.8 MP) และ 8000×5000 (40 MP) เป็น PNG สังเคราะห์ที่บีบอัดได้ดี วัดแต่ละกลุ่ม 3 รอบ พร้อม accepted/rejected workloads แยกกัน: 256 DET polygons; REC numeric transport ประมาณ 3.33 MB ต่อ image/13.33 MB ต่อ batch; 1001 polygons; 100001 REC characters; streaming body 65 MiB จับ CPU user/system, RSS, cgroup current/peak/stat/events/swap และ decoded bytes ที่อ่าน รายละเอียด/หลักฐาน hashes อยู่ [JSON](memory-reliability-evidence.json)

Original swap-default trials และ no-swap trials แยกกลุ่ม ไม่รวมเป็น baseline เดียวกัน `memory.peak`/events สะสมภายใน container lifetime ส่วน phase peaks เป็น sampled current; sampler ไม่รับรองว่าจะจับ transient ทุกจุด จึงใช้ kernel peak ตรวจขอบบนด้วย RSS อาจรวม shared pages ที่ไม่ถูก charge ให้ cgroup นี้ ห้ามเอา RSS ลบ cgroup แล้วตีความเป็น heap

## ผลสำคัญ

| Experiment | ก่อน | หลัง | ข้อสรุป |
|---|---:|---:|---|
| Transport-only kernel peak, worst of 3, 4×13.32 MB, no swap | 155.66 MB | 47.10 MB | ลดประมาณ 69.7%; เป็น transport probe ไม่ใช่ full backend |
| Separate tracemalloc peak, 4×3.33 MB | 21.32 MB | 1.66 MB | ลดประมาณ 92.2%; latency ของ instrumented run ไม่ใช้เทียบ normal run |
| Image-only 40 MP at 512 MB, no swap | OOMKilled=true 3/3 | ผ่าน 3/3; peak 368.98 MB | Full-image copies เป็น defect ที่ reproduce ได้ใน local |
| Baseline 40 MP reference, RAM local 1024 MB | peak 684.36 MB | PNG และ 8 crop hashes ตรง candidate | ใช้ยืนยัน bytes เท่านั้น ไม่อ้าง baseline ผ่านที่ 512 MB |
| Final full backend 12.8 MP, tasks4/no swap, worst kernel peak | — | 488.37 MB | เหลือประมาณ 4.6%; ไม่ถึง proposed 20% |
| Final full backend 40 MP, tasks4/no swap | — | 512.00 MB | แตะ limit แม้ observed OOM/kill=0 |
| Final 40 MP tasks2/no swap — local alternative | — | 476.15 MB | เหลือประมาณ 7.0%; ยังไม่ถึง proposed target |
| Final 40 MP RAM1024 MB/tasks4/no swap — local alternative | — | 599.20 MB | เหลือประมาณ 41.5% สำหรับ workload นี้เท่านั้น |

![Before and after resource comparison](memory-reliability-comparison.png)

![Allocation probes](memory-reliability-allocations.png)

## Allocation และ latency

Baseline json.loads materialize transport floats ทั้งก้อนก่อนทิ้ง: isolated heap instrumentation ยืนยัน retained allocation ที่ json.loads ส่วน raw-only extraction เก็บ scalar/geometry ก่อน pop archive เดิม และ recursive sanitizer เดิมสร้าง object tree ใหม่

Incremental event filtering ลด heap แต่ใช้ CPU เพิ่มกับ numeric tokens: transport probe median latency ~0.724→1.752 s; matched full numeric workload 12.8 MP ที่ swap limit เดียวกัน ~7.34→11.29 s. แยก no-swap final ~11.88 s; ต่างรอบ/สภาพ warm state มีผล ไม่ตีความเป็น model speed. Matched full-workflow worst kernel peak ~512.21→489.66 MB ยังคงไม่ถึง proposed margin เพราะ rejection/file-cache pressure. Full backend CPU time ต่อ phase และ timings ทุก trial เก็บใน evidence

Prototype ที่ parse ตรงจาก HTTP stream ไม่ผ่าน: string 65 MiB ที่ยังไม่จบทำให้ parser เก็บ token ใหญ่พร้อมกันหลาย request เกือบเต็ม limit และ rejection median ~37.21 s จึงเลิกใช้แบบนั้น Temporary spool ปฏิเสธก่อน parse ลด rejection มาแถว 1–2 s แต่เปลี่ยนความกดดันบางส่วนจาก anon heap เป็น file cache ตัวอย่างก่อน image fix ที่ peak: anon ~267.10 MB, file ~219.37 MB, kernel ~12.79 MB

BatchGateway ยัง deepcopy เฉพาะ owned result slices เพื่อแยก mutation ระหว่าง callers; allocation probe พบ copies ของ slices เล็กกว่าต้นทุน parse มาก จึงไม่ถอด isolation เพื่อประหยัด RAMอย่างคาดเดา Result order/aliases และ 30+4 splitting ยังมี tests

Image decoding/crops ใช้ native Pillow/OpenCV buffers ซึ่ง tracemalloc ไม่ได้สะท้อนทั้งหมด จึงดู RSS/cgroup โดยตรง Full-page np.asarray และ EXIF/RGB copies เดิมทำให้ image-only 40 MP baseline ถูก local OOM kill จริง ไม่ใช่หลักฐานสาเหตุ historical HTTP502

## Integrity และข้อจำกัด

- Final worker interruption: 48 unique persisted outputs; checkpoint IDs ทั้ง 32 เดิมยังอยู่; attempts=2 มี final ID lists ใน ignored synthetic evidence และ hash ให้ตรวจ ไม่รัน inference แบบ exactly-once หาก crash ก่อน commit
- Prediction hashes ของ accepted/rejected results ตรง baseline; EXIF orientations 1–8, RGB/RGBA/L/P/CMYK conversion และ ROI metadata/PNG/hash มี exact reference tests
- Stream limit ไม่ใช่ heap limit: retained JSON data tree, scalar string tokens, HTTPX decompression allocations และ native image allocations ยังขยายได้ การอ่าน 64 KiB ไม่รับรองว่า decoder ภายในจะไม่ allocate มากกว่านี้
- Temporary disk budget อาจถึง 4×64 MiB ต่อ active worker/manager พร้อม file cache; ต้องมี writable temp directory/พื้นที่ว่าง/permissions และ admission ระดับ deployment ไม่ถือว่า spool เป็น durable storage
- 40 MP fixture บีบอัดได้ดี ไม่ครอบคลุมภาพ noise/high-entropy, PDF ทั้ง 500 หน้า, ทุก model shape, multiple instances หรือ adversarial compressed responses ไม่มีข้อสรุปว่าทุก input ที่ config อนุญาตผ่าน resource envelope นี้
- ไม่ลด MAX_IMAGE_PIXELS, task/field/batch/response limits เพื่อให้ผ่าน ตัวเลือก tasks2/RAM1024 เป็น local measurements เท่านั้น ต้องอนุมัติ operational settings แยกก่อนใช้จริง
- Proposed ≥20% free เป็นเกณฑ์ประเมินในงานนี้ ไม่ใช่ Production requirement ที่ได้รับอนุมัติแล้ว

## Recommendation

**NO-GO / BLOCKED สำหรับ 512 MB default envelope** แม้ tests ความถูกต้องผ่านและ allocation ลดลงมาก ทางเลือก 1024 MB มีหลักฐานดีกว่าสำหรับ bounded synthetic workload นี้ แต่ยังต้องทดสอบ representative non-sensitive images/PDF, compressed outputs, sustained sessions, temp storage และ public request admission ก่อนถือว่า Production-safe ไม่มีการอัปเกรด Production ในงานนี้

ดู [release readiness](production-release-readiness.md) สำหรับ policy, deployed read-only checks, incident และแผนอนุมัติ release ที่ยังไม่ execute
