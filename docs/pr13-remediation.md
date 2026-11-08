# PR #13 — NO-GO remediation

วันที่ 8 พฤศจิกายน 2569 · branch `fix/ocr-workflow-regression-audit` · reviewed baseline `7b8caf279d8eade1eb1f86b3b1334f36b028e424`

**คำตัดสิน Production: NO-GO** — remediation ลด code/test blockers แต่ยังไม่ผ่าน authorization, uploads preservation และ memory envelope ไม่มีการ merge/deploy/restart Production หรืออ่าน private uploads/แก้ Production DB/secrets REQ-12 OUT OF SCOPE

## ข้อบกพร่องจริงที่แก้

1. `PUT /api/pipelines/{id}` ของ Dynamic configuration เรียก `adapter_classes` ที่ถอดไปแล้วและเกิด 500 การแก้ยอมรับเฉพาะ name/enabled; model/routing ยังต้องผ่าน `/definition` validation เดิม ไม่คืน built-ins ให้ startup เพื่อรองรับ test เก่า Regression ใช้ config/adapter จริง ตรวจผลย้อนหลังและ model options ไม่เปลี่ยน
2. Terminal Job elapsed ใช้ `finished_at` ที่ persist แล้ว หรือ `updated_at` สำหรับ historical fallback ไม่ใช้เวลาเปิดหน้าปัจจุบัน; เวลาไม่เพิ่มหลัง completed/partial_success/failed/cancelled ข้อมูลผิด/ขาดแสดง `—` ไม่สร้าง duration เอง
3. Debug ปิด fail closed ไม่มี diagnostics/toggle/localStorage bypass จนกว่าจะมีสิทธิ์จริง **ไม่ถือว่าสิ่งนี้แก้ authorization ของ API ที่มีอยู่แล้ว**

Dataset ไม่เปลี่ยน behavior: explicit refresh ล้าง selection อยู่แล้ว; unavailable sample ยังเลือกเพื่อ bulk exclusion ได้แต่ exportable=0 Backend ตรวจ original ทุก export และไม่มีภาพ/label ทดแทน การแก้ availability ที่เคยทดลองถูกถอนเมื่อพิสูจน์ว่า refresh handler ปัจจุบันป้องกัน stale selection แล้ว

Terminal Results empty200/bounded errors/abort/4xx/read-only recheck ที่แก้ใน 7b8caf2 รักษาไว้และทดสอบซ้ำ ไม่ reimplement worker/parser/GT/metrics/storage

## Triage baseline ทั้งหมด

[ตารางแยกทุก failure](pr13-failure-triage.md): 55 backend + 34 Playwright ไม่ลบ/skip tests ไม่ปิด assertions หรือย้อน production behavior ให้เหมือน fixture เก่า

- Built-in IDs ไม่ถูก seed แล้ว: fixture สร้าง current dynamic definitions และ OCRModel จริงเฉพาะ DB ทดสอบ ใช้ real manager/adapters กับ HTTP mock ที่ตอบจำนวน inputs จริง
- UI single-case ใช้ Durable Jobs: รอ create202→poll terminal→persisted results; ไม่คืน synchronous `/run` ให้ browser Batch pages ที่ยังใช้ `/run-pages` จริงคง endpoint เดิม Backend legacy API coverage ยังอยู่
- ยืนยัน GT ก่อน analytics, newmm ตาม WER ปัจจุบัน, synchronized Whole/Sub GT, compact metadata/raw-text deduplication, logs/error events ที่เลิก persist และ pipeline count ตาม configuration เป็น semantics ก่อน PR นี้ ไม่แก้ metric engine/normalization/labels
- UI selectors ใช้ metrics cell/character summary/model editor/disclosures ปัจจุบัน; mock ErrorInsights มี schema จริงแทน TestCase ที่ผิดชนิด การกด Deep detail ด้วย mock เดิมทำให้หน้า crash ไม่ใช่หลักฐานว่า API production ส่ง schema ผิด

## Requirements ที่ขอทบทวน

| REQ | ผลและขอบเขต |
|---|---|
| 03 | ต้องซ่อน Field labels โดย outlines ยังอยู่เท่านั้น ไม่เพิ่ม requirement labels-without-outlines จากการตีความเดิม ตรวจ canvas pixels ของ badge เปลี่ยน/เส้นกรอบเดิมคงอยู่ พร้อม immutable selection/zoom; ไม่มีการแก้ ROI coordinates |
| 06 | terminal duration จาก persisted timestamp และ frozen ผ่าน clock advance/reload ทุก terminal status; active timer/units/checkpoints แยกเหมือนเดิม |
| 11 | ไม่ reproduce duplicated full GT/OCR panels ด้วย valid ErrorInsights; แต่ละ field มี GT/Raw OCR หนึ่งบล็อก ส่วน error excerpts ต่อ event ตั้งใจเก็บไว้ ไม่มีการ deduplicate ตัวอักษรที่ซ้ำจริงหรือทิ้ง combining-mark/deletion evidence |
| 13 | isolated oversized geometry/REC/response, concurrent configs, 30-image split, retry/cancel, worker kill/recovery และ missing-source cases; ไม่มี production capacity certification และยังมี memory gate |
| 14 | Debug เพิ่มเติมปิดแล้ว; real API authorization ยัง BLOCKED มี [rollout plan](pr13-security-rollout.md) แยก ไม่เพิ่ม schema/auth refactor แอบใน PR |
| 12 | OUT OF SCOPE |

REQ01/02/04/05/07/08/09/10 ตรวจซ้ำด้วยชุด browser/Backend เดิม รวม PDF, local scrolling/focus, Unicode, modal, partial failures และ source recovery ตามขอบเขต tests ไม่อ้าง Production acceptance

## Resource evaluation ที่ execute ใหม่

ตรวจ `setup-resource.py` และ script ที่ถูกเรียกก่อน execute: local Docker project `ocrlab-remediation` เท่านั้น สร้าง image จาก dependency image ในเครื่องแบบ `--network none`, DB/uploads แยก, mock ภายใน isolated network, loopback-only ports ไม่มี CDGS/private credentials/production connection ใช้ approval review ปกติ ไม่มีการ bypass คำสั่งที่เคยถูกปฏิเสธ

Backend limit **512,000,000 bytes / 1 CPU**, observer 50 ms; RSS/HWM เป็น process, cgroup รวม cache/สมาชิกกลุ่ม ไม่ใช่ค่าเดียวกัน ห้าสถานการณ์แรกใช้ process/container ต่อเนื่อง จึงมี high-water และ memory.events สะสม ไม่ใช้ตัวเลขสะสมเป็น peak เฉพาะ request

| Scenario | ผล | RSS สูงสุด (bytes) | cgroup sampled peak (bytes) | OOM / kill |
|---|---|---:|---:|---|
| 256 DET regions ต่อ input, 2 Fields × 4 Pipelines | 8/8 unique success, 12.50s | 264,024,064 | 480,260,096 | 0 / 0 |
| numeric REC transport ~3.33MB/input, 4×4, 8 regions, 1,000 Thai chars/line | 16/16 unique success, 6.88s | 331,018,240 | 511,283,200 | 0 / 0 |
| 1,001 DET regions | 4 truthful INVALID_OCR_RESPONSE, 0.60s | 356,442,112 | 511,963,136 | 0 / 0 |
| REC 100,001 chars | 4 truthful INVALID_OCR_RESPONSE, 0.51s | 298,496,000 | 445,808,640 | 0 / 0 |
| 65MiB response >64MiB limit | 4 truthful RESPONSE_TOO_LARGE, 0.81s | 481,845,248 | 511,922,176 | 0 / 0 |
| Controlled worker kill/start, 12×4 | 48/48 unique success, attempt2, 103.52s | 281,300,992 | 403,771,392 | 0 / 0 |

Worker preserves **32/32 observed committed checkpoint IDs**, no duplicate persisted output IDs. Harness initially stopped on temporary proxy502 during intentional kill/start; reconnect handling corrected and worker-only scenario rerun successfully. This is not represented as a clean first attempt of all scenarios

Kernel `memory.peak` หลัง replacement สุดท้ายอ่านได้ 233,033,728 bytes, memory.events OOM/kill=0 ขอบเขตคือ container หลัง restart เท่านั้น ส่วน phase sample/HWM ครอบคลุม process ก่อนและหลัง interruption จึงไม่ใช่ peak window เดียวกัน

**Resource gate remains:** cgroup.max events reach 1,039 cumulatively; lowest sampled headroom 36,864 bytes in excessive-geometry phase. No observed OOM does not mean safety margin. Concurrency/large serialization under 512MB needs a documented supported envelope and repeated representative trials (or justified resource/batch changes tested separately), not an unmeasured production memory change. Historical 502 cause remains unconfirmed; local pressure is not proof of historical OOM. In-flight upstream calls may repeat after a crash before checkpoint commit; durable output deduplication is not exactly-once remote inference

Safe aggregates and artifact hashes: [results JSON](../postman/staging/pr13-remediation-results.json). Full synthetic observer/XML/logs and reviewed harness remain ignored in `.runtime/remediation/`; temporary browser.cjs is reviewed as an isolated local probe and remains uncommitted

## Final validation

Validation results are recorded after the final complete run; intermediate runs are retained separately. No interim browser failure is called passed until its corrected test is rerun. Fresh PostgreSQL upgrade through 0011→0012 and schema drift check passed; no migration/environment/provider setting added

- Backend final rerun: **545 passed / 0 failed / 0 skipped**, PostgreSQL tests executed, 117.12s มี upstream library deprecation warnings 2 รายการ
- Ruff app/tests: PASS รวม import-order เดิมที่แก้เฉพาะการจัด imports; whole backend: **1 baseline I001** ที่ `alembic/versions/0010_dynamic_pipelines.py:2` คง historical migration ไว้ ไม่อ้างว่า whole-repo Ruff ผ่าน
- Database: clean local PostgreSQL →0011→0012 head, 15 tables, `alembic check`: no new upgrade operations ไม่แตะ Production DB
- Secret scan: exact private environment values/DB password และ token/private-key patterns ไม่พบใน tracked/intended new files; `.env` และ `.runtime` ignored/untracked ไม่มี payload/credentials ใน aggregate JSON

## Remaining release gates

1. Real backend authentication/authorization and tenant/ownership rollout — [security plan](pr13-security-rollout.md)
2. Production originals inventory + approved encrypted backup + complete restore drill + durable target + write freeze/final delta — [runbook](pr13-upload-recovery-runbook.md). No production upload inspected or copied here; missing originals require restore/re-upload
3. Supported resource envelope with meaningful headroom; no inference-capacity claim from these synthetic samples

Keep Draft PR #13. Local verified changes may be committed/pushed to its feature branch for another independent review; no merge/release authorization implied

## Final executed browser/tool results

- Full Playwright: **188 passed / 0 failed / 0 skipped**, fresh isolated PostgreSQL and synthetic source files; complete suite หลังแก้ครั้งสุดท้าย ไม่ใช้ focused result แทน full run
- TypeScript / ESLint / Next.js production build: PASS; standalone output present. React review: no new fetch waterfall/provider/ROI state rewrite; terminal timestamp helper is pure, Debug fails closed
- REQ03 screenshot pixels: labels เปลี่ยนจริง, outlines คง pixels เดิม และหาย/กลับเมื่อลอง toggle outlines; ใช้ decoded screenshot pixels เพราะ cross-origin canvas ไม่อนุญาต getImageData ไม่แก้ CORS/product เพื่อผ่าน test
- Final diff/secret/link scans: PASS. No tests deleted or skipped; two obsolete browser titles renamed to describe synchronized GT/current completeness behavior. Baseline 55 backend +34 browser are resolved in the current full runs
- Full Ruff remains 1 pre-existing migration import-order finding; app/tests Ruff PASS. No new migration, environment variable, deployment change, raw upstream model rewrite or production data access
- Local resource-test containers stopped after evidence capture; encrypted/private production files never entered this test stack

## Files included for review

**Backend application**

- `backend/app/db/seed.py`
- `backend/app/pipelines/dynamic.py`
- `backend/app/services/auto_roi_service.py`
- `backend/app/services/dynamic_pipeline_service.py`
- `backend/app/services/pipeline_config_service.py`

**Backend tests**

- `backend/tests/catalog_fixture.py`
- `backend/tests/conftest.py`
- `backend/tests/e2e_app.py`
- `backend/tests/test_api.py`
- `backend/tests/test_batch_logs_delete.py`
- `backend/tests/test_benchmark_pipeline.py`
- `backend/tests/test_detection_reading_order.py`
- `backend/tests/test_document_dataset_management.py`
- `backend/tests/test_error_analysis_dataset.py`
- `backend/tests/test_fields_roi.py`
- `backend/tests/test_global_layout.py`
- `backend/tests/test_hutch_fine_tune_v2.py`
- `backend/tests/test_insight_source_fields.py`
- `backend/tests/test_pdf.py`
- `backend/tests/test_pipeline_update_compatibility.py`
- `backend/tests/test_privacy_and_database.py`
- `backend/tests/test_real_boundaries.py`
- `backend/tests/test_thai_ft_v2.py`
- `backend/tests/upstream_fixture.py`

**Frontend application**

- `frontend/components/GlobalWorkspace.tsx`
- `frontend/components/OCRJobRunner.tsx`
- `frontend/components/SafeDebugPanel.tsx`

**Frontend library**

- `frontend/lib/api.ts`
- `frontend/lib/job-timing.ts`

**Frontend tests**

- `frontend/tests/batch-logs-delete.spec.ts`
- `frontend/tests/benchmark.spec.ts`
- `frontend/tests/console.spec.ts`
- `frontend/tests/dataset-errors.spec.ts`
- `frontend/tests/fields-roi.spec.ts`
- `frontend/tests/global-comparison.spec.ts`
- `frontend/tests/global-layout.spec.ts`
- `frontend/tests/job-result-verification.spec.ts`
- `frontend/tests/job-timing.spec.ts`
- `frontend/tests/pdf.spec.ts`
- `frontend/tests/release-b.spec.ts`
- `frontend/tests/thai-ft-v2.spec.ts`
- `frontend/tests/workflow-audit.spec.ts`
- `frontend/tests/workflow.spec.ts`

**Documentation**

- `docs/ocr-workflow-regression-audit.md`
- `docs/pr13-failure-triage.md`
- `docs/pr13-independent-review.md`
- `docs/pr13-remediation.md`
- `docs/pr13-security-rollout.md`
- `docs/pr13-upload-recovery-runbook.md`

**Aggregate evidence**

- `postman/staging/pr13-remediation-results.json`
