# Bounded workload — local release candidate

สถานะ 10 พฤศจิกายน 2569: **G6 final candidate ผ่าน local verification แล้ว** ดู [release gates](production-release-gates.json), [รายงาน](production-release-and-live-e2e.md) และ [หลักฐานสุดท้าย](g6-release-evidence.json) การผ่าน local gates ไม่ใช่ผล deployed E2E ซึ่งตรวจแยกหลัง auto-deploy

## ขีดจำกัดใหม่ที่ผู้ใช้อนุมัติให้ลดและทดสอบ

| รายการ | เพดาน candidate |
|---|---:|
| ภาพที่ decode / crop / raster หน้า PDF | 2,000,000 พิกเซลต่อภาพ/หน้า |
| ความยาวแต่ละด้าน | 8,000 พิกเซล |
| ไฟล์อัปโหลด | 10 MiB |
| PDF | 20 หน้า; เลือกและประมวลผลทีละหน้า |
| DPI เริ่มต้น PDF ใหม่ | 140; A4 ประมาณ 1157 × 1638 พิกเซล |
| งาน OCR ที่ประมวลผล | 1 งานต่อ container |
| งาน queued + running ทั้ง workspace | 5 งาน; เต็มตอบ 429 |
| Fields / Pipelines ที่เลือกต่อการรัน | 12 / 6 |
| ผลคูณ Fields × Pipelines ต่อ job | 24; เช่น 4 Fields × 6 Pipelines หรือ 12 Fields × 2 Pipelines |
| DET regions ต่อ Field | 128; มากกว่านี้ปฏิเสธทั้งผลของ Field/Pipeline นั้น ไม่ตัดบรรทัด |
| ข้อความ OCR ต่อ Field | 32,768 ตัวอักษร; มากกว่านี้เป็น failure ไม่ตัดข้อความให้ดูเหมือนสำเร็จ |
| Field / adapter task ที่ทำพร้อมกัน | 1 / 1 |
| ภาพต่อ physical Gateway batch | 1 |
| กลุ่ม perspective crops | รวมไม่เกิน 1 MP หรือ 30 เส้น; เส้นที่ใหญ่กว่านี้แยกเดี่ยว |
| Gateway response ที่อ่านหลัง decompress | 8 MiB ต่อ physical response |
| HTTP body อื่น | 1 MiB; upload เพิ่มพื้นที่ multipart framing 64 KiB |
| คำขอที่ใช้ image memory | 1 active + 1 waiter; รอไม่เกิน 2 วินาที จากนั้น 429 / Retry-After 5 |

`/api/upload-config` เป็นข้อมูลสาธารณะเฉพาะ limits ไม่ส่ง secrets หน้า Upload และ workflow แสดงขีดจำกัดจริง ค่าขนาดไฟล์ชื่อ `*_MB` ใน code ใช้หน่วย MiB (1,048,576 bytes)

ค่าจาก environment ที่สูงกว่า release ceilings ถูกจำกัดใน `Settings`; ตั้งค่าต่ำกว่าได้ `PDF_RENDER_DPI` ยังปรับได้ระหว่าง 72–400 แต่ทุกหน้าต้องผ่าน pixel ceiling เสมอ Existing Railway ตั้ง200DPI จึงเตรียมเปลี่ยนเฉพาะ existing non-secret variable `PDF_RENDER_DPI=140` แบบskipDeploysก่อน merge ที่อนุมัติ ไม่เปลี่ยน DPI/ROI ของ PDF records เดิม

## พฤติกรรมและข้อมูลเดิม

- ไม่ย่อ/เพิ่มคุณภาพภาพที่อัปโหลดเพื่อหลบขีดจำกัด ภาพเกินเพดานตอบ 413 ก่อน `Image.load()`
- อ่านเฉพาะ header ของภาพใน storage ก่อนอ่าน source ทั้งไฟล์; อ่านไฟล์เต็มแบบมี byte bound ป้องกัน canonical PNG เก่าขนาดใหญ่ การ crop ใช้ pixel grid ของ source เดิม
- PDF ใหม่เก็บ DPI และขนาด raster ลง metadata การเลือกหน้าและ ROI ใช้พิกัด raster ของหน้านั้น PDF เดิมยังใช้ DPI ที่บันทึกไว้ ไม่ rerender แล้วเขียนทับ ROI เก่า
- ผลเก่า/GT/metadata คงอยู่ การประมวลผลซ้ำที่เกินเพดานใหม่ถูกปฏิเสธ; ไม่สร้างภาพทดแทน ไม่ลบ source หรือผลเดิม
- Fields เดิมที่มีมากกว่า 12 ยังเปิดอ่าน/แก้ GT ได้ แต่ไม่รับรันใหม่เกินเพดาน งานเก่าที่มี checkpoints จะเก็บผลที่ commit ไว้ หาก source ไม่ผ่าน policy ใหม่ worker จะจบอย่างปลอดภัย
- Dataset ใช้ crop จาก source + confirmed GT เท่านั้น ไม่เปลี่ยน labels เป็น OCR หรือ metrics การ export source ที่เกิน policy ตอบ error แทนไฟล์ปลอม
- การแบ่ง batch และลด concurrency คงลำดับ ผล OCR/model selection/geometry และ idempotency semantics; upstream error หรือ response ใหญ่เกินเพดานเป็น failure ที่เห็นได้ ไม่ตัดข้อความให้ดูเหมือนสำเร็จ
- API เก่า `/run` และ PDF batch ยังอยู่เพื่อ compatibility และอยู่ภายใต้ admission เดียวกัน polling/ผลที่บันทึก/GT ไม่รอ image slot

## การตรวจและข้อจำกัด

ใช้ Docker local 512,000,000 bytes / 1 CPU / no swap พร้อม synthetic Gateway ไม่ใช้เอกสารหรือ inference Production การผ่าน functional tests ไม่เท่ากับผ่าน memory gate ต้องตรวจ peak cgroup รวมกับ RSS, memory.stat/events และสถานะ OOM ของ container

ผลของ 8 / 6 / 4 MP และกรณี PDF ต่อด้วย prefill ที่ไม่ผ่านเก็บเป็นหลักฐาน ไม่ตัดออกเพื่อทำให้รายงานเขียว Fresh process ไม่ได้หมายถึง filesystem cache ว่าง; cache charging ระหว่าง containers ต่างกัน จึงรายงาน anon/file/kernel แยกและไม่ใช้ Python heap แทน RAM รวม

Counterexamplesของcandidateก่อนแก้คือ452,136,960/452,472,832bytesและstressที่มากกว่าเพดานใหม่ยังเกินtarget เก็บไว้เป็นประวัติ ไม่ใช้warmcacheลบล้าง หลังแก้ compact lexicon/native lifetimesและประกาศ24-unit/128-region/32768-character envelope: mixed3รอบ393,707,520/384,008,192/383,287,296bytes และfullresource/recovery404,197,376bytes ทั้งหมดต่ำกว่า409,600,000target ไม่มีOOM/pressuremax การวัดนับfilecacheครบและเติมchargedfilecacheให้ถึง220MBก่อนเริ่ม เพื่อไม่อาศัยwarmhostcacheอย่างเดียว

PDF แบบ global Field/Prefill ซ้ำใน process เดิม และ small/typical-image OCR อย่างละสามรอบผ่านด้าน functional รายละเอียดแต่ละ phase อยู่ใน evidence/report ทุก Gateway ใน memory probes เป็น synthetic mock ไม่ใช่หลักฐานคุณภาพ OCR หรือ capacity ของ CDGS จริง

ระบบเป็น **public shared workspace** โดยตั้งใจ ใครเข้าถึง URL ได้สามารถอ่าน/แก้/ลบข้อมูลและตั้งค่าได้ ไม่มี authentication/access-control claim Admission เหล่านี้ช่วยจำกัด memory/queue แต่ไม่รับประกันโควตาฟรีหรือป้องกัน anonymous compute/DB abuse ทั้งหมด

ไม่มี migration ใหม่ ไม่มี environment variable ใหม่ ไม่มี paid resource / provider migration และ REQ-12 ยัง OUT OF SCOPE
