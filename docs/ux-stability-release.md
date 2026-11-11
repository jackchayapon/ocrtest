# OCRLab — UX & Stability Bugfix Release

ฐาน: PR #14 / `68991cd9a93f776a72a1fe81cb633e040fd6d4c2` · Branch `fix/ux-stability-after-multifield` · 11 พฤศจิกายน 2569

เอกสารนี้บันทึกผล local ก่อน merge ส่วน SHA/deployment IDs และผลตรวจ UI หลัง deploy เก็บใน release journal และคำอธิบาย PR เมื่อดำเนินการจริง ไม่มีการอ้างผล Production ล่วงหน้า

| ข้อ | อาการและสาเหตุที่ตรวจพบ | สิ่งที่แก้และหลักฐาน | ผล local |
|---|---|---|---|
| 1 | Auto Layout ใช้ fallback12 ก่อน config มาถึง และไม่มีทาง retry config | ไม่ใช้ค่าจำลองตรวจเพดาน; รอ backend config สำเร็จ, ปิดปุ่มระหว่างโหลด/ล้มเหลว, retry และกัน double click; mock โหลดช้า/503 แล้วเพิ่ม25กรอบพร้อมรักษา manual ROI; เกิน80ปฏิเสธทั้งชุดไม่ตัดทิ้ง | PASS |
| 2 | busy banner ถูกแทรกเหนือ Preview, ความสูง grid ตาม controls ที่ขยาย และ busy callback cleanup ส่ง false ทุก poll | กำหนดความสูง Preview อิสระในหน้า Pipeline/GT, คง layout editor เดิม, ไม่แทรก busy banner, ไม่กระตุก callback และข้าม ResizeObserver ค่าเดิม; ตรวจ node/ขนาด/zoom/pan/scroll และจำนวน image GET เท่าเดิมหลังเริ่ม/poll Job จำลอง | PASS |
| 3 | GET image/PDF metadata ติด image lock ที่ worker ถือทั้ง Job; browser Image.onerror ไม่มี bounded retry | PNG ที่เก็บแล้วตรวจ header และ stream64KiB, PDF ที่เคย render ใช้ cache หน้าตรงกัน; cache miss ยังผ่าน lock เดิม; GET retry429/503 ตาม Retry-After สูงสุด5ครั้ง/30วินาที,404แสดง missing ทันที; reload จำลองไม่ POST Job ซ้ำ | PASS |
| 4 | เปอร์เซ็นต์เป็นเฉพาะ OCR units แต่ข้อความสื่อว่า workflow เสร็จ ทั้งที่ hidden prefill ยัง running | แยกข้อความอ่าน OCR ครบ/เตรียมGT/ตรวจผลก่อนเปิด/สิ้นสุด จากสถานะและcurrent_pipeline_idเดิม;99/99ไม่แสดง overall100%; refreshยังField4/33; terminalยังรอ persisted results; GT partial/unavailable ใช้สถานะเดิมตามจริง | PASS |
| 5 | ปุ่มใน text preview เรียกเพียง selection ไม่ส่ง focusRequest | ภาพและปุ่มข้อความใช้ navigation เดียวกัน, เปลี่ยน Sub-fields, จัดกึ่งกลาง internal list, highlight และ focus preventScroll; revisionรองรับคลิกซ้ำ;ทดสอบ1/10/33/80และEnter โดยข้อความ/scrollหน้าคงเดิม | PASS |
| 6 | สถิติและ crop ขยาย inline ทำให้ตารางยาว และไม่มี overlay ที่เหมาะกับภาพ | native dialog96vw/94dvh, one-at-a-time, content scroll, Escape/focus restore/background lock; lazy statistics/crop, handoffจากstatsไปcropในdialogเดียว;ตรวจUnicodeไม้โท/emoji, PDFหน้า2/ROI,zoom/fit/pan/reset,desktop/mobile;ไม่เพิ่มOCR | PASS |
| 7 | Upload รอ lock2วินาทีแล้ว429เป็น generic error; clientไม่มี admission retry หรือ synchronous click guard | รักษา heavy lock; เพิ่ม response marker เฉพาะก่อนเข้ารับไฟล์, expose Retry-After ผ่านCORS; clientรอได้12attempts/60s, HTTPattempt30s, ยกเลิกระหว่างรอ,ไม่ retry network/5xx ที่อาจรับแล้ว;ทดสอบหนึ่งเอกสาร,timeout/ambiguous outcome/cancel | PASS |
| 8 | Loading/error/modal/resource lifecycle ในเส้นทางข้างต้นไม่สอดคล้องกัน | เก็บ ROI/typedGT, cleanup AbortController/objectURL/stream/temporary cache, ป้องกัน duplicate actions, recoverable errors และ mobile overlays; regression ของ navigation,storage-denied,GT,PDF,export ยังผ่าน | PASS |

## ผลทดสอบใหม่

- Targeted Backend **43 passed / 0 failed / 0 errors / 0 skipped**, PostgreSQL local, exit0: `test_preview_admission.py`, `test_pdf.py`, `test_workload_policy.py`, `test_privacy_and_database.py`.
- Targeted Playwright **62 passed / 0 failed / 0 skipped**, exit0: UX stability13เคสใหม่ รวม config race,preview,refresh,prefill,Field navigation,overlay,upload; และ regression ใน `global-selection`, `character-insights`, `job-storage`, `ocr-jobs`, `workload-limits`.
- TypeScript, ESLint, Next.js production build, Ruff ของ Backend ที่แก้ และ diff ผ่าน Secret scan ทำก่อน commit ไม่รวม `.env`/`.runtime`.
- Docker source ตรง **85/85** Python files. รายละเอียดและ SHA256 ของ artifacts อยู่ใน [หลักฐาน](ux-stability-evidence.json).
- ไม่แก้ schema/model/migration จึงไม่ต้องเปลี่ยนฐานข้อมูลหรือทำ migration compatibility run ใหม่.

ผล PR #14 เดิม Backend679 / fullPlaywright214 / 40–60–80 benchmark เป็น **baseline เดิม** ไม่ใช่การรันใหม่ในงานนี้ ไม่มี real CDGS inference, liveOCR หรือ 40/60/80 stress run ใหม่

## Resource admission และความปลอดภัยของข้อมูล

Focused mixed case ใช้ local synthetic2MP image + PDFสองหน้า + Job2FieldsกับmockGateway อ่าน PNG/PDFซ้ำระหว่างถือ worker lock พร้อม upload429ก่อนรับไฟล์แล้ว retry201 สำเร็จ ภาพมี hash เดิม และ Job เดิมจบโดยไม่ซ้ำ

ภายใต้ **512,000,000 bytes / 1 CPU / no swap**: kernel memory.peak **376,279,040 bytes**, เหลือ **26.508%**; RSS high-water ของ final process168,824,832bytes; OOM/memory.max events0 รวม file cache โดยไม่หักออก และมี initial charged cache reserve220MB ไม่ใช่การพิสูจน์ capacity ของCDGSหรือ workload80Fieldsใหม่

Preview read แยกเป็นหนึ่ง stream ที่อ่าน64KiBต่อครั้ง โดยไม่ decode PNG; PDF cache เป็น disposable private cache สูงสุด8MiB/16ไฟล์ ที่สร้างภายใต้ image lock เดิม ไม่แทน source และไม่ถูกใช้เป็น OCR input. Cache miss ระหว่าง OCR ยังตอบ429ให้ retryตามขอบเขต หากต้นฉบับหายต้อง404แม้มี cache. Cacheเขียนไม่ได้ใช้ bounded fallback;ไม่แก้หรือลบต้นฉบับ

Upload marker `X-OCRLab-Retry-Safe: pre-admission` ออกเฉพาะ WorkloadGuard ที่ยังไม่เรียก route; API429จากที่อื่นไม่มี marker นี้จึงไม่ใช่สิทธิ์ retry POST อัตโนมัติ. ไม่อ้าง exactly-once สำหรับ network failure หลัง server อาจรับไฟล์; UI แนะนำตรวจประวัติก่อนส่งซ้ำ

ไม่มี Job-status/database field ใหม่ การแยก phase เป็น presentation จาก server fields เดิม ไม่เปลี่ยน Job ID/checkpoints. Header ใหม่และการ expose Retry-After เป็น backward-compatible. Image/PDF/model request, normalizer, inference concurrency, incremental persistence, GT/CER/WER/Exact Match และ80/3/240 limits **ไม่มี diff จากฐาน**

## ไฟล์ที่เปลี่ยน

- Backend: `api/routes/documents.py`, `core/workload.py`, `main.py`, `services/storage_service.py`, `services/preview_service.py`.
- UI: `GlobalWorkspace`, `DocumentViewer`, `OCRJobRunner`, `GlobalGroundTruthForm`, `GlobalFieldEvaluation`, `CharacterErrorSummary`, `FieldErrorDetails`, `SourceCropPreview`, `WorkflowUpload`, `LargeDialog`, `ReadOnlyImage`.
- Client helpers: `api.ts`, `upload-admission.ts`, `use-preview-source.ts`.
- Tests: `test_preview_admission.py`, `test_pdf.py`, `ux-stability.spec.ts`, `ux-stability-fixture.ts`, `global-selection.spec.ts`, `character-insights.spec.ts`, `job-storage.spec.ts`.
- Docs: เอกสารนี้และ `ux-stability-evidence.json`. Generated `next-env.d.ts` คืนเฉพาะเนื้อหาเดิมหลัง build; ไม่รวม runtime probes/logs/private fixtures ใน commit.

Tests เก่าที่คาด inline stats และการคลิก Field โดยไม่เปลี่ยนโหมดปรับให้ตรง requirement ใหม่พร้อมคงการตรวจ Unicode/filter/export/GT. PDF storage assertion ตรวจ original bytes เท่าเดิม พร้อมระบุ private bounded cache โดยชัดเจน ไม่มีการลบ/skip/ลด assertions เพื่อให้ผ่าน รอบแรกพบ checkbox Deep-detail ถูก reset ก่อน click จบ แก้ให้ checked จนปิด overlay; หลักฐานรอบล้มเหลวยังเก็บไว้

## Release / ข้อจำกัด

ดำเนินการ normal newPR review/merge และ auto-deploy ไป projectเดิมหลัง required checks ผ่าน ไม่ force push/ไม่ re-merge PR14/ไม่เพิ่มค่า Hosting. หลัง deploy ตรวจ exactSHA, health, crash/OOM/5xx และ Production UI โดยใช้เอกสารสังเคราะห์เล็กเท่านั้น

Auto Layout และสถานะ Job/GT/ผลวิเคราะห์ที่ต้องใช้โมเดลในการตรวจ UI Production จะใช้ browser-controlled responses และรายงานว่าเป็น simulation ไม่เรียก CDGS หรือสร้าง real OCR Job. การทดสอบ upload/Preview backend จริงแยกจากการจำลองนี้

PDF cache อาจถูก evict หรือหายหลัง redeploy; cold pageต้องรอ image admission. Upload รอครบกำหนดอาจต้องลองภายหลัง Job ยาวเสร็จ. Public shared workspace และ ephemeral upload storage ยังคงความเสี่ยงที่ยอมรับจากเดิม ไม่มีระบบ login/backup ใหม่ ไม่มีคำรับประกัน uptime100%. REQ-12 OUT OF SCOPE
