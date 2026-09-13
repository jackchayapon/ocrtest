# ผลตรวจสอบ OCR Testing & Benchmark

## Controlled local live review - 2026-09-13

- No application code changes in this review. Existing 79 passing backend tests and 11/11 Playwright suite results from 2026-09-11 remain applicable. Ruff, frontend typecheck and lint were checked again and passed; the existing production build served this browser smoke.
- All three pipelines succeeded on a synthetic 1600 x 2200 image (13 normalized boxes each). Hutch Crop received 43,759,767 response bytes (41.73 MiB); Hutch Full received 48,939,977 bytes (46.67 MiB). Both exceeded the old 16 MiB cap and passed the effective 64 MiB cap (67,108,864 bytes). Their sanitized stored responses were 3,929 and 3,939 bytes. Request IDs, Gateway duration, service and model remained available.
- A five-page synthetic PDF was submitted once through the UI with pages 1, 3, 5 selected and all three pipelines. All nine runs succeeded. SQL audit timestamps prove page 1 saved at 12:44:53.191551 UTC before page 3 started at 12:44:53.195706; page 3 saved at 12:45:41.032615 before page 5 started at 12:45:41.037190. Page 5 saved at 12:46:15.648616. Page concurrency was 1; pages 2 and 4 were not processed.
- Smoke setup caveat: uploading cleared the category selected before upload, so the live batch initially had no category. Categories were then applied to all three saved cases and edited independently without repeating OCR. Batch-time category propagation remains covered by the passing automated test. Request-building review confirms categories are never passed as model hints, including Auto ROI.
- The browser verified logs, level filtering and pagination, cancelled deletion, then explicitly confirmed deletion of the disposable page-1 case. SQL checks confirmed dependent runs/metrics/joins were removed without orphan metrics; category definitions, original PDF, page-3/page-5 cases and an unrelated case remained. Missing-case GET/DELETE returned 404.
- Persisted responses and logs were checked without printing raw payloads or secrets. No embedded image data, credentials, full OCR text or Ground Truth were found in application logs; heavy Paddle image data was redacted before persistence.
- Only the dedicated local PostgreSQL review database was migrated: current/head `0005_app_logs`, `alembic check` reports no drift. Neon was not accessed or migrated. No app deployment was performed.
- The initial sandbox-blocked requests did not reach the Gateway. After health verified network access outside the sandbox, one real three-pipeline image run and one three-page batch were performed, without stress testing or increasing the limit.
- Sequential batch remains request-bound and intended for the current single-worker/local MVP, not a distributed background-job system.

## Feature implementation validation - 2026-09-11

This pass adds the bounded 64 MB Gateway response setting, sequential PDF page batches, category analytics details, confirmed history deletion, and safe application logs.

- Backend: **79 passed**, 2 dependency deprecation warnings; Ruff passed.
- Frontend: typecheck, lint and production build passed; Playwright **11/11 passed**.
- Local PostgreSQL: `alembic upgrade head` to `0005_app_logs` and `alembic check` passed with no schema drift.
- Tests prove ascending single-page execution, continuation after page failure, independent saved cases, transactional deletion, document preservation, and safe filtered logs.
- No live OCR requests, Neon migration, application deployment, commit or push in this pass. Docker was used only to start local PostgreSQL for validation.
- Batch processing requires one FastAPI worker/instance and an open streaming connection. Committed page results survive interruption. See [batch-activity.md](batch-activity.md).

The following sections retain **previous validation evidence**. Their live Gateway, Neon and Docker results do not validate this uncommitted feature revision.

อัปเดต 11 กันยายน 2026 ตามคำยืนยันล่าสุดจากเจ้าของ Hutch: Hutch Full ใช้ภาพเต็มเท่านั้น ไม่ใช้ ROI และไม่ crop ในแอป

## สถาปัตยกรรม

- Mint: canonical ROI crop → shared Gateway `engine=custom`
- Hutch Crop: canonical PNG เดียวกับ Mint → shared Gateway `engine=paddle`
- Hutch Full: ภาพเต็มหรือหน้า PDF ที่เลือก → shared Gateway `engine=paddle` ไม่มี ROI ใน payload หรือ diagnostics ของ run; พิกัดกล่องอ้างอิงภาพเต็ม
- Auto ROI: ภาพเต็ม → `/api/v1/document-layouts` เป็นตัวช่วยเตรียม ROI ของ Mint/Crop ไม่ใช่ Pipeline ที่สี่

ทุกตัวใช้ MODEL_GATEWAY_BASE_URL และ MODEL_GATEWAY_API_KEY ร่วมกัน URL เก่าในฐานไม่ override runtime ทั้งสอง Hutch ส่ง text_det_unclip_ratio=1.7, text_det_thresh=0.25, text_det_box_thresh=0.6

Hutch Full บันทึก input SHA-256/ขนาด/byte size/format และ Gateway tracing จริง ใช้ crop_stage=full_image และ crop fields เป็น null ลบตัวกั้น contract เดิมแล้ว ไม่สร้าง migration ใหม่ ผลเก่าที่ใช้ semantics อื่นยังเก็บในฐานแต่ไม่นำมาปะปนใน Matrix ปัจจุบัน

## ผลเรียก Gateway จริง

ใช้ key จาก private environment ไม่บันทึกค่า key ทดสอบภาพสังเคราะห์ข้อความ OCR BENCHMARK TEST 12345 ไม่มีเอกสารผู้ใช้ ไม่มีการเขียนผล live smoke เข้า Neon

| คำขอ | ผล |
| --- | --- |
| GET /api/v1/health | HTTP 200 |
| GET /api/v1/readiness พร้อม Bearer | HTTP 200 |
| Mint OCR | สำเร็จ มีข้อความและ 1 box; crop 740×110; Gateway 206.73 ms |
| Hutch Crop OCR | สำเร็จ มีข้อความและ 1 box; crop 740×110; Gateway 705.84 ms |
| Hutch Full OCR | สำเร็จ มีข้อความและ 1 box; full image 800×240; ไม่มี ROI; Gateway 621.81 ms |

HTTP 401 จาก key เก่าเป็นผลก่อนหน้า ไม่ใช่สถานะปัจจุบัน ไม่มี blocker ของ authentication หรือรูปแบบคำขอทั้งสาม Pipeline ที่ทราบในรอบนี้ Auto ROI live ผ่านจากหนึ่งคำขอ: HTTP 200, data/meta envelope ถูกต้อง ได้ 3 suggestions อยู่ในขอบเขตภาพ 900×400 เวลา Gateway 2505.84 ms ผลนี้ยืนยัน integration และโครงสร้างพิกัด ไม่ใช่ข้อสรุปด้านความแม่นยำหรือประสิทธิภาพ

## Validation

- Backend: **65 passed**, รวม local PostgreSQL; Ruff ผ่าน มี dependency deprecation warnings 2 รายการ
- เพิ่มกรณี Hutch Full ไม่ใช้ ROI แม้ ROI ไม่ถูกต้อง ตรวจ no local crop, full PNG bytes, ไม่มี multipart ROI, engine=paddle และพิกัดภาพเต็ม
- PDF test ยืนยัน full page bytes ต่างจาก canonical crop และ Mint/Hutch Crop ใช้ bytes เดียวกัน
- Frontend typecheck, lint, production build ผ่าน
- Playwright **10/10 ผ่าน** รอบนี้ ครอบคลุมภาพ/PDF, ROI, ผลสาม Pipeline, GT/metrics, save/reopen, dashboards, settings และ responsive
- Docker backend/frontend rebuild ผ่าน ใช้ runtime environment; ไม่มี secret build args
- คง schema `0004_real_inputs` ไม่ reset Neon และไม่ลบ production records

## Security และหลักฐาน

.env คงเป็น private file ถูก ignore และไม่ track; .env.example มี key ว่าง ไม่มี per-pipeline credential/host source of truth และไม่มี product Mock fallback ผลเก่าที่ archive ยังคงเก็บไว้

รายงาน JSON อยู่ใน [validation-evidence.json](validation-evidence.json) หลักฐาน source เดิมอยู่ใน gateway-contract-evidence.json ส่วนคำยืนยันล่าสุดของเจ้าของ Pipeline มีลำดับเหนือข้อสันนิษฐานเดิม
