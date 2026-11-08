# OCRLab — Production release readiness

ตรวจ 9 พฤศจิกายน 2569 · **NO-GO / BLOCKED — รออนุมัติ release แยก** · REQ-12 OUT OF SCOPE

## Candidate และขอบเขต

- Local code candidate: **`f8c7949ba5e11e162e59b340b37d0dc607a38b54`**, branch `perf/ocr-memory-reliability`, derived from `607af992867dd33425597d22efb5d7f489fbadc7`. Documentation-only handoff commit follows; no application changes after validation. ไม่มีการ push branch นี้
- [Draft PR #13](https://github.com/jackchayapon/ocrtest/pull/13): HEAD `607af992867dd33425597d22efb5d7f489fbadc7`, unmerged, Draft; ไม่แก้ branch/PR นี้ในงาน preparation
- Vercel Production: READY, commit `695bf4b0f3355653ea4c82102e6586debaac9c2b`, deployment `dpl_G1EMQukFRhHdtVp2chQcCmj98nbT`
- Existing PR #13 Preview: READY, commit `607af992867dd33425597d22efb5d7f489fbadc7`, deployment `dpl_4RoCD8MbdSKSA4uUNZhdR7Cb8Ke9`; browser ถูก Vercel Authentication ป้องกัน
- Railway active/source deployment: `468e0200-d1be-41b9-a201-2288b8be0fc0`, commit `64c23a7c996b73c89f37f9cfef112a65489e5028`; metadata รายงาน SLEEPING. Commit `695bf4b` เป็น SKIPPED ที่ backend ไม่อ้างว่า backend รัน SHA เดียวกับ frontend
- แก้เฉพาะ verified allocation/image-copy defects และ canvas readout layout regression; ไม่เปลี่ยน OCR routing, GT, metrics, checkpoint IDs, schema หรือ Production configuration

## เหตุผิดพลาดระหว่างตรวจ Preview — เปิดเผยและแก้ตามอนุมัติ

คำสั่ง `vercel@65.12.1 env run --project ocrtest --scope jackchayapon-s-projects --environment development -- node .runtime/pre-release/preview-oidc.cjs` ที่ตั้งใจใช้ existing OIDC authentication กลับสร้าง project/deployment ใหม่ชื่อ `preview-oidc` ขัดกับข้อห้ามของงาน ไม่มีการถือว่าการกระทำนี้เป็น smoke-test success หรือ release ที่ได้รับอนุมัติ Root cause การตีความคำสั่ง CLI ยังไม่ยืนยัน จึงหยุดใช้วิธีนี้ ไม่ลอง syntax ที่อาจ deploy ต่อ

- Project ที่สร้างผิด: `prj_IaGoHlZkZmcACOmMCsrLlYdQVIvY`
- Deployment เดียวใน project: `dpl_GUE3BFRZpUFUw1qo5yZTTtsCpZQ6`
- Read-only inventory พบ source file เดียว `src/preview-oidc.cjs`; ไม่พบ `.env`/uploads ใน file tree; project env list มี 0 รายการ ไม่อ้างผลนี้แทนการตรวจ deployment-specific runtime env ที่ไม่ได้อ่าน
- ผู้ใช้อนุญาตลบเฉพาะ project นี้อย่างชัดเจนแล้ว ใช้ `project delete preview-oidc --confirm-name preview-oidc --scope jackchayapon-s-projects` สำเร็จ ตรวจ project ID ซ้ำได้ 404
- OCRLab Production deployment ID/commit ยังเท่าเดิมหลัง cleanup. ไม่ merge, ไม่เปลี่ยน Railway, ไม่เปลี่ยน Production secrets/DB/uploads
- จึง **ไม่สามารถอ้างว่าไม่มี deployment ใดเกิดขึ้นตลอด assignment** ได้ แม้ไม่มี OCRLab release deployment และ resource ที่สร้างผิดถูกลบตามอนุมัติแล้ว

## Local verification

| Test | Status | หลักฐาน/ขอบเขต |
|---|---|---|
| Full backend incl. PostgreSQL | PASS | **583 passed**, 0 failed, 0 skipped, exit 0, 106.26 s; 2 dependency deprecation warnings |
| Gateway/ROI image regression | PASS | Included in full backend: 17 transport memory cases, 21 exact image contract cases, prior routing/429/batching/recovery/GT/Dataset tests |
| Full Playwright — final candidate | PASS | **206 passed**, 0 failed, child exit 0, 4.3 min หลัง footer fix; ไม่ใช้ historical totals แทน |
| Canvas follow-up | PASS | 36 tests ผ่าน: global workflow + audit รวม repeat-each=3 หลังแก้ footer; ก่อนหน้านั้น audit-only 5/5 |
| TypeScript / ESLint | PASS | รันใหม่หลัง footer fix, exit 0 ทั้งคู่ |
| Production build | PASS | Final local E2E runner build; การ build local ไม่ใช่ deployment |
| Ruff app/tests/changed probes | PASS | exit 0; historical migration0010 I001 ไม่ suppress และไม่ได้อ้าง whole-backend Ruff ผ่าน |
| Alembic/local PostgreSQL | PASS | Fresh local DB clean→0011_gt_prefill→0012_ocr_jobs, 15 tables, drift check ผ่าน; isolated DB ถูกลบหลังตรวจ |
| Public-workspace policy probes | PASS | 2 isolated synthetic tests: anonymous read/write/job/export/admin ตาม policy และ Gateway key ไม่ถูก serialize/foreign model URL ถูกปฏิเสธ |
| Secret/diff/link scans | PASS | Final candidate scan ไม่พบ private secret matches/broken report links; raw `.runtime`, credentials, synthetic source files ไม่เข้า Git |
| GitHub CI for PR #13 | PASS เฉพาะ Vercel | Combined statuses ที่ connector คืนมี Vercel success เท่านั้น ไม่อ้าง remote full regression CI; local branch ยังไม่มี GitHub CI |

Full browser runs ระหว่าง remediation ที่ล้มไม่ถูกซ่อน: รอบหนึ่ง 205/206 ล้ม pixel assertion เพราะพิกัดอ่านก่อน screenshot แล้ว fit transform เปลี่ยน; อีกหนึ่ง 205/206 ล้ม ROI movement tolerance ระหว่าง pointer-triggered footer reflow. เก็บ traces ไว้ ignored path. ไม่เพิ่ม tolerance, skip หรือถอด assertions; synchronize screenshot frame และแก้ product footer ให้ geometry คงที่

## Verified defects และ integrity

1. Gateway buffering/JSON allocations: bounded RAM spool + incremental allowlist/redaction ลด transport-only kernel peak 155.66→47.10 MB และ instrumented Python heap 21.32→1.66 MB; response limit เดิม, reject-before-parse, ปิด streams/temp files เมื่อ success/error/cancel/disk failure
2. Full-image copies: local image-only 40 MP baseline ถูก OOMKilled=true 3/3 รอบที่ 512 MB; candidate ผ่านทั้ง 3. PNG และ crop SHA ตรง reference ที่รัน baseline ด้วย RAM local 1024 MB. EXIF orientations/modes/metadata มี exact tests. ไม่อ้างว่านี่เป็น root cause ของ historical HTTP502
3. Canvas footer: pointer coordinate text ทำให้ flex wrap และ Fit scale เปลี่ยนขณะลากได้จริง ปรับเป็น readout rows คงที่พร้อม horizontal overflow โดยไม่ตัด coordinates. เพิ่ม pointer-enter/leave transform assertion; pixel comparisons ยัง exact
4. Worker final candidate interruption: 48 unique saved outputs, 32 checkpoint IDs เดิมคงอยู่, attempts=2. ไม่มี schema/job identity change. Upstream calls ก่อน commit ยังอาจซ้ำหลัง crash ไม่อ้าง exactly-once inference
5. OCR text/polygons/model params/GT/CER/WER/Exact Match ยังคง tests และ prediction hashes เปรียบเทียบ baseline ไม่เปลี่ยน Dataset labels เป็น prediction/metrics

## Memory envelope และทางเลือกที่วัด

รายละเอียดพร้อม [charts](memory-reliability.md) และ [sanitized metrics](memory-reliability-evidence.json). ทุก workload ใช้ synthetic image/isolated DB/mock Gateway. Default tasks4, fields8, upstream batch4/cap30 และ response64MiB ไม่ลดเพื่อให้ผ่าน

| Final workload, 1 CPU/no swap, 3 trials | Worst kernel peak | Verdict |
|---|---:|---|
| 12.8 MP, RAM512 MB, tasks4 | 488.37 MB | FAIL proposed ≥20% free |
| 40 MP, RAM512 MB, tasks4 | 512.00 MB | FAIL มี memory pressure; observed OOM/kill=0 ใน final workflow ไม่เท่ากับ safety |
| 40 MP, RAM512 MB, tasks2 — local alternative | 476.15 MB | FAIL target; เหลือ ~7.0% |
| 40 MP, RAM1024 MB, tasks4 — local alternative | 599.20 MB | PASS เฉพาะ bounded workload นี้: ~41.5% free; ไม่ได้เปลี่ยน Production |

Accepted cases กับ rejected bodies ต้องประเมินแยก; file cache ของ spooling ยังดัน current ใกล้ limit. Parser numeric CPU/latency สูงขึ้น. High-entropy images, worst compressed responses/HTTPX decoder allocations, PDF500pages, multiple instances และ sustained public abuse ยังไม่พิสูจน์ ไม่มี defensible full supported envelope ที่ 512 MB จึงยัง BLOCKED ไม่ลด configured source limits เงียบ ๆ

## Shared public workspace — user-confirmed policy

ผู้ใช้ยืนยันว่า **ทุกคนใช้ workspace เดียว และเปิดสาธารณะโดยไม่ล็อกอิน ทุกคนอ่าน/แก้ไข/ลบข้อมูลและตั้งค่า Pipeline ได้** จึงไม่มี requirement แยกเจ้าของเอกสาร/tenant และไม่เพิ่ม login/ownership migration ที่ขัด policy

- Server routes ของ Documents/images, Jobs/results, GT, History, Dataset/ZIP/Excel/evaluation exports และ pipeline administration ไม่มี authentication/ownership dependency จริง นี่เป็น public permission model ที่ผู้ใช้ยืนยัน ไม่อ้างว่า endpoint เหล่านี้ได้รับ private access control
- ใช้ synthetic local clients ตรวจ policy ไม่อ่าน private Production records. UUID/CORS/UI toggle ไม่ถูกนับเป็น authorization
- Debug diagnostics panel ยังคง fail-closed. Gateway credentials/DB strings ต้องอยู่ backend; same-origin resolver, redirect blocking, schema validation และ redaction tests คงอยู่
- Public compute/storage/queue abuse ยังเป็น P1 operational risk: ต้องมี approved request/queue/storage budgets และ monitoring. ไม่ใช่เหตุให้แอบเพิ่ม login หรือเปลี่ยน Production firewall ในงานนี้
- ผู้ใช้/ผู้ดูแลต้องเข้าใจว่าเอกสาร/GT และ admin changes ไม่มีขอบเขตความเป็นส่วนตัวระหว่างผู้เยี่ยมชม หาก policy เปลี่ยนเป็น restricted ให้ใช้ [security rollout](pr13-security-rollout.md) ฉบับแผน ไม่ถือว่าได้ implement แล้ว

## Neon และ historical compatibility

- PASS: schema/code head `0012_ocr_jobs`, clean migration/local drift และ historical records/job recovery ผ่าน isolated tests ไม่มี migration ใหม่ ไม่มี ALTER/DROP/UPDATE บน Production
- BLOCKED: read-only metadata attempt ไปยัง Neon target ใน private `.env` ได้ OperationalError category **timeout**; ไม่แสดง connection string/message ไม่อ่าน document rows. ยังไม่ได้เทียบ Railway secret identity ดังนั้นไม่รับรอง current Production revision จาก attempt นี้
- PASS: Production `/api/health` ตอบ PostgreSQL connected; นี่ไม่ยืนยัน revision, PITR หรือ restore readiness
- ก่อน future release ต้องยืนยัน DB identity/current revision แบบ read-only อีกครั้ง. ถ้า head0012 อยู่แล้วไม่ต้อง apply migration; ถ้ายัง0011 ต้องตรวจ additive0012 แล้วใช้ normal Alembic path หลังอนุมัติ ห้าม reset/downgrade เพื่อ rollback code

## Uploads — user-accepted ephemeral loss

Railway inventory มี 0 volume mounts; health ระบุ local storage ready. ผู้ใช้ยอมรับ historical originals อาจหายเมื่อ deploy ในอนาคต จึง **ไม่ใช้ historical-upload preservation เป็น unconditional release blocker** ไม่มี intentional deletion/export/access ของ originals ในงานนี้

Neon metadata/GT อาจยังอยู่แต่สร้าง originals คืนไม่ได้: History ยังแสดง saved text/metrics ตามที่มี; image/crop ที่ต้นทางหายต้องแสดง unavailable; Dataset sample นั้นเลือก/export ไม่ได้และ API คืน clear error; valid sources export ได้ตามเดิม ไม่ทำ fake image หรือเงียบ drop label. Recovery ต้อง restore จากสำเนาที่มีจริงหรือ re-upload. Durable volume/private object storage กับ [recovery runbook](pr13-upload-recovery-runbook.md) เป็นแผน optional ที่ต้องอนุมัติก่อนทำจริง

## Existing Production smoke — public Chromium

URL จริง `https://ocrtest-sandy.vercel.app/`, Chromium headless153; desktop1440×900, laptop1280×800, mobile390×844

| Check | Status | Result |
|---|---|---|
| `/`, `/history`, `/matrix`, `/dataset`, `/settings/pipelines` HTTP/shell | PASS | 15/15 route×viewport checks HTTP200, JavaScript executes, static UI/assets render |
| Navigation / hydration | PASS | Desktop/laptop client navigation และ mobile menu state toggle ใช้งาน; page exceptions0 |
| Responsive shell | PASS | document overflow0 ใน checked states; full private-record layouts ไม่ได้โหลด |
| API connectivity / CORS / health | PASS | Browserจริง GET health จาก Railway สำเร็จทุก viewport; ACAOตรง Production origin, DB connected/storage ready |
| Data-backed History/Matrix/Dataset content | BLOCKED | Abort record/aggregate APIs ก่อนออก network เพื่อไม่อ่าน unrelated private records ไม่มี mock responses |
| Console/network errors | PASS ภายใน scope | Console errors19รายการรวม3viewportsเป็น ERR_BLOCKED_BY_CLIENT จาก deliberate privacy guard; ไม่พบ naturalHTTP4xx/5xx หรือ page exception ใน allowed requests; ไม่อ้างว่าไม่มี Production errorsทั่วระบบ |
| Production write/OCR/E2E | NOT RUN | ตามข้อห้าม ไม่มี upload/job/GT mutation/export ผ่าน Production |

Screenshots/browser JSON อยู่ ignored `.runtime/pre-release/` ไม่ commit. Screenshots ทดสอบได้เฉพาะ shell/error states ที่ไม่มี records

## Existing Preview smoke และ isolation

URL `https://ocrtest-2in9lld36-jackchayapon-s-projects.vercel.app/` ตอบ redirectไป `https://vercel.com/login` (final HTTP200 เป็น login page) **BLOCKED** สำหรับ application hydration/responsive/navigation/API smoke. ไม่ใช้ localhost แทนผลนี้ ไม่อ้าง Vercel READY/build success เป็น E2E pass

Preview backend/Neon/uploads/Gateway credential isolation ยัง **UNKNOWN/BLOCKED**. ไม่พบ isolated online backend+DB ที่ยืนยันแล้ว. ห้ามทำ write workflow ผ่าน Preview จนยืนยัน isolation และเข้าถึงด้วย supported authenticated browser path. ไม่สร้าง staging/deployment เพิ่มเพื่อแก้ blocker นี้

## Remaining P0/P1/P2

| Priority | Finding | Action before release |
|---|---|---|
| Policy — ไม่ใช่ finding | ไม่มี owner isolation | เป็น public/shared policy ที่ผู้ใช้ยืนยัน; ไม่มี P0 ownership blocker ตาม requirement นี้ และห้ามอ้าง private workspace protection |
| P1 | 512 MB envelope ไม่ผ่าน target/เข้าใกล้ limit; response cache/decode/native allocations | เลือกและอนุมัติ resource/admission strategy แล้ว validate representative workload; local1024เป็นทางเลือกที่วัดแล้วไม่ใช่การอนุมัติ upgrade |
| P1 | Public unbounded compute/storage/queue abuse | กำหนด resource/request budgets และ incident response; verify upstream capacity/limits โดยไม่ stress Production |
| P1 | Preview authenticated E2E/isolation ยังไม่ยืนยัน | ยืนยัน existing isolated target/access หรือบันทึก explicit acceptance decision ก่อน future writes |
| P1 | Current Production Neon revision/identity ยังไม่ยืนยัน | แก้ readonly metadata connectivity และตรวจ schema ก่อน rollout |
| P2 | Numeric incremental parsing CPU/latency tradeoff/temp disk footprint | วัด actual response shapes/temp I/O และ latency budget; ไม่เพิ่ม retry เพื่อกลบ |
| P2 | Legacy runPipelines storage handling, retry-budget ≠ hard deadline | ดู findings เดิมใน [audit](pr13-final-independent-audit.md); ยังไม่อ้างแก้ทุก legacy path |
| P3 | Historical migration0010 Ruff I001 | คงแยกรายงาน ไม่แก้ migration เก่าเพื่อ style |
| Closed process incident | สร้าง preview-oidc deployment ผิดและลบตามอนุมัติ | หยุดใช้ CLI access path ที่ทำให้เกิดเหตุ เก็บ evidence; OCRLab Production untouched |

## Future release procedure — DOCUMENTED ONLY

### A. Publish/review/merge หลัง explicit authorization ใหม่

1. ตรวจ clean tree และ reviewed local code SHA ที่รายงานด้านบน. ห้าม push ในงานนี้เพราะ existing Git integration เคยสร้าง Preview ของ branch ที่607และไม่ได้ยืนยัน ignore-build rule ที่ป้องกัน deployment
2. เมื่ออนุญาต push/Preview แยกแล้วจึง publish `perf/ocr-memory-reliability` และสร้าง stacked Draft PR targeting `fix/ocr-workflow-regression-audit`; ยังไม่มี PR number จึงไม่แต่งหมายเลข
3. ตรวจ PR #13 HEAD ยัง607; ถ้าเปลี่ยนให้ตรวจ diff/regression ก่อน. Required checks: full backend/PostgreSQL, full Playwright, TS, ESLint, build, app/tests Ruff, schema, secret/diff และ resource decision. Verify branch protection/review requirements ด้วยผู้ดูแล; ไม่ bypass
4. หลังอนุมัติ release แยกและ gatesผ่าน: merge **PR #13 ก่อน**, จากนั้น retarget stacked candidate PR ไปmainและ mergeเป็นลำดับถัดไป. Keep history ไม่ force push/amend/rewrite. ถ้า exact merge tree ต่างจาก tested tree ต้องตรวจ relevant/full checks ตามความเปลี่ยนแปลง

### B. Railway backend

1. ก่อน push/mergeที่ auto-deploy: ยืนยัน intended project/service/environment/source branchmain, watch paths และ resource decision. ปัจจุบันsource mainยืนยันแล้วแต่ dashboard watch pathsยังไม่ยืนยัน; อย่า assume skipถูกต้อง
2. ยืนยัน Neon identity/revision0012/schema โดยread-only. ทำ additive migrationเฉพาะที่จำเป็นหลังอนุมัติ; ไม่ seed/resetข้อมูลใหม่เพื่อแก้ปัญหา. ไม่มี migrationใหม่จาก memory candidate
3. Operatorอนุมัติ RAM/temp disk/admission strategy ก่อน codeเริ่มserve. ห้ามนำlocal1024MBผลทดลองไปใช้Productionโดยอัตโนมัติ
4. รอ existing Git integration build/deploy exact intended SHA ไม่สั่งmanualdeploymentซ้ำ. ตรวจ install ijson3.6.0/runtime pins, import errors, non-root temporary-file permissions/free space, startup migration และ worker lifecycle
5. Health200 + DB connected/storage ready, worker lease/heartbeat/checkpoint, queued/running/terminal transitions. ตรวจ restarts/OOM/memory.events/current/peak/file/anon/CPU/temp disk/5xx/429 โดยไม่ log OCR/GT/credentials

### C. Vercel frontend

1. ตรวจ Git integration/environment/root `frontend`, NEXT_PUBLIC_API_BASE_URLตรง backend; conditional standalone ยังคงเดิม. Credentialsไม่อยู่frontend build
2. รอ native production build READYที่ approved SHA; ตรวจassets/hydrationและbackend CORSสำหรับdomainจริง. Preview READYไม่เท่ากับ Production verified
3. ห้ามเปลี่ยนprotection/promote/rollback/ใช้CLI bare deployโดยไม่มีอนุมัติ. ใช้ supported deploy-specific inspection commandที่อ่านอย่างเดียวเมื่อตรวจ

### D. Post-deployment acceptance หลังอนุมัติเท่านั้น

Real Playwright Chromium ที่ `https://ocrtest-sandy.vercel.app/`: synthetic small imageหนึ่งภาพ, ≤2Fields, OCR Jobหนึ่งงาน → Auto/Manual ROI → เลือกpipelineที่พร้อม → Job202/poll/reload → saved results/GT Check/Confirm → evaluation/error evidence → History → Comparison → valid Dataset/ZIP/Excel. ตรวจ labelเป็นconfirmedGT และ imagecrop/source mapping. ไม่ใช้เอกสารผู้ใช้ ไม่เรียกโมเดลซ้ำเพื่อread-onlychecks

ตัวworkflowนี้ **NOT RUN บนProductionในงานปัจจุบัน**. หลังfuture deploymentต้องตรวจค่าพิกัด/PNG hashes/polygons/confidence/meta/jobIDs/duplicatecountsจริง รวมmissing-source graceful state และviewportทั้งสาม

### E. Monitoring / rollback

- หยุด acceptance เมื่อ5xxเพิ่ม, OOM/restart, wrong model/ROI, duplicate persisted outputs, GT/metric corruption, schema mismatch หรือsource missingที่ไม่แสดงerrorชัดเจน
- แยก app/gateway/platform/DB/temporary-storage failureจากrequestID/status/errorcode โดยไม่เก็บrawdata
- หลังอนุมัติincident actionจึงrollbackไป last known healthy backend (`64c23a7…` deployment468e0200…) และfrontend (`695bf4b…` deploymentdpl_G1EM…) เมื่อยืนยันartifact/config/schema compatibilityและplatformrollbackavailabilityแล้ว; ห้ามอ้างว่าปุ่มrollbackพร้อมใช้โดยไม่ได้ตรวจ
- Code rollbackไม่คืน ephemeral files และไม่ undo Job/GT transactions; ไม่downgrade/drop0012หรือresetNeon. Preserve checkpoint rows/lease fencing และmetadata; sourceที่หายคืนได้จากbackupจริงหรือre-uploadเท่านั้น
- Public workspaceต้องมี operator/contact/incidentbudget และCDGS escalationrequestIDs. กำหนดmonitoringwindowและความรับผิดชอบก่อนเปิดrelease ไม่ดำเนินขั้นตอนเหล่านี้อัตโนมัติ

## Final verdict

**Release preparation: BLOCKED as documented.** Local engineeringลดallocationและแก้verifiedcanvasdefectแล้ว แต่512MBfull-envelope, Preview verification/isolation และProduction schema verificationยังไม่ผ่าน ไม่มี merge/Production release; เกิด unintended separate deploymentหนึ่งครั้งและลบหลังผู้ใช้อนุมัติแล้ว ดังนั้นไม่ใช้ประโยค “No merge or deployment was performed” โดยไม่บอกเหตุการณ์นี้

**Awaiting explicit user approval for Production Release.** การอนุมัตินั้นต้องแยกจากการรับทราบรายงานและผล tests. REQ-12 remains OUT OF SCOPE.
