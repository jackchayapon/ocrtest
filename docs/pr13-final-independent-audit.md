# PR #13 — Final independent code and release audit

วันที่ 8 พฤศจิกายน 2569 · **Production: NO-GO** · REQ-12 OUT OF SCOPE

## ขอบเขตที่ตรวจจริง

- Reviewed PR HEAD: `3fe647f2683b2af4ecb87a81d454739febbd532b`
- Previous reviewed HEAD: `7b8caf279d8eade1eb1f86b3b1334f36b028e424`
- Main baseline: `695bf4b0f3355653ea4c82102e6586debaac9c2b`
- GitHub ยืนยัน Draft=true, merged=false, branch `fix/ocr-workflow-regression-audit` ก่อนตรวจ
- ตรวจ PR diff 73 ไฟล์ และ remediation commit 50 ไฟล์ รวม application/test/fixture changes ไม่ใช้ผลสีเขียวแทน code review
- ไม่มีการอ่าน private Production data/uploads, สำรองข้อมูลจริง, เปลี่ยน secrets, restart, merge หรือ deploy

## Executive verdict

Remediation แก้ Dynamic PUT ที่เกิด 500, terminal timer และปิด Debug UI ได้จริง แต่พบ regression เพิ่มใน PR: navigation acknowledgement เข้าถึง Web Storage โดยไม่ดัก exception ทำให้หน้า GT ใช้ไม่ได้เมื่อ browser ปฏิเสธ storage นอกจากนี้เส้นทาง submit เดิมจัดการ storage ก่อน `try/finally` จึงอาจค้างหรือแสดงงานที่ API รับแล้วเป็น failure

แก้เฉพาะ frontend job workflow และเพิ่ม negative tests; ไม่เปลี่ยน worker, API, model routes, metrics, GT persistence, Dataset หรือ schema ผล local validation ไม่อนุญาต production โดยอัตโนมัติ

## Findings ตาม severity และที่มา

| ระดับ | Finding / ที่มา | หลักฐานและสถานะ |
|---|---|---|
| P0 | API ไม่มี user/tenant ownership authorization — inherited main | `backend/app/api/dependencies.py:9`, `api/routes/documents.py:103`, `ocr_jobs.py:44`, `dataset.py:45`, `pipelines.py:19`: dependency ให้ DB/service ไม่ตรวจ principal; UUID/CORS ไม่ใช่ authorization ขอบเขตนี้ไม่ได้ทดสอบบน Production |
| P1 | ความคงทนของ uploads และ recovery ยังไม่ยืนยัน — operational | ยังไม่มีหลักฐาน complete inventory + encrypted backup + restore drill + durable destination; DB backup สร้าง originals คืนไม่ได้ ห้าม redeploy เพื่อทดลอง |
| P1 | 512,000,000-byte memory envelope ไม่มี safety margin ที่ป้องกันได้ — operational/inherited allocation paths | cgroup sample เหลือ 36,864 bytes และ max events 1,039; ไม่มี OOM ที่สังเกตไม่เท่ากับ production capacity proof |
| P2 FIXED | GT acknowledgement ทำให้หน้า GT ล้มเมื่อ storage ถูกปฏิเสธ — introduced PR | `GlobalWorkspace.tsx` เดิมอ่าน localStorage/เขียน sessionStorage โดยไม่ guard; negative read/write tests เดิมล้มจริงทั้งสองกรณี |
| P2 FIXED | Submit ใช้ Web Storage ก่อน try/finally/ก่อน adopt accepted job — inherited main | `OCRJobRunner.tsx`: ตอนนี้เก็บ pending idempotency key ใน ref สำหรับ retry, adopt API job ก่อน optional storage writes และ cleanup ใน finally |
| P2 remaining | Legacy compatibility `runPipelines` ยังพึ่ง localStorage ที่ไม่ได้ guard — inherited main | `frontend/lib/api.ts:96` ไม่ใช่ Global workflow runner ที่แก้รอบนี้ ควรแก้แยกพร้อม legacy UI negative-path coverage; ห้ามอ้างว่าทุกหน้าของแอปใช้ได้โดยไม่มี storage |
| P2 limitation | Gateway 30s retry budget ไม่ใช่ hard wall-clock request deadline | `model_gateway.py:232`: ตรวจเวลาก่อน sleep/retry แต่ request ที่เริ่มแล้วใช้ HTTP timeout ของตัวเอง; synthetic clock probe ยืนยัน successful second response หลัง budget ได้ จำกัด attempts=3 จริง ไม่อ้างทุก request จบใน30s |
| P3 | Legacy removed registry references ยังคงอยู่ | `pipeline_config_service.py:25,100`: NULL mode ถูก `BenchmarkRepository.config` กรอง404 และ public schema ไม่ให้ empty mode จึงไม่ใช่ reachable normal API500; invalid empty-string DB record นอก validation ยังเสี่ยง ควรถอด dead branch/ทำ fail-closed ใน cleanup แยก |
| P3 | Historical Ruff I001 และเอกสาร snapshot เก่า | migration0010 import order ไม่แก้ย้อนหลัง; requirement table เก่าที่กล่าวถึง Debug toggle ถูก supersede โดย disabled component และผลล่าสุดนี้ |

## Dynamic Pipeline / contracts / fixture integrity

- ทดสอบผ่าน public create/update API: name/enabled เปลี่ยนได้, mixed request ที่ใส่ endpoint ถูก422ก่อนแก้ชื่อ, endpoint/query/model options ไม่เปลี่ยน, retired NULL config update/test-connection เป็น404
- `DynamicPipelineInput` ยังตรวจ definitions; compatibility update ไม่คืน built-in adapters และไม่เปลี่ยน DET/REC versions/variants
- Test-only catalog เขียน current-schema records ตรง DB จึง **ไม่ใช่หลักฐาน create-validation** ด้วยตัวเอง แต่ real manager/adapters ยัง execute และ `test_dynamic_pipelines.py` กับ independent API probe ตรวจ public validation แยก
- Shared upstream fixture ตอบตามจำนวน multipart images จริง แต่ใช้ข้อความซ้ำ จึงไม่พิสูจน์ ordering ด้วยตัวเอง; direct adapter tests ยังคงตรวจ distinct ordered REC text, polygons, perspective crops, exact params และ34 inputs→30+4
- Metrics, Dataset service และ durable worker ไม่มี application diff เทียบ main; empty-GT semantics, newmm WER, confirmed-GT analytics และ lean raw/log behavior มีอยู่ใน baseline ไม่ได้แก้ engine เพื่อผ่าน fixture
- 89 historical failures มี55 backend +34 browser rows ใน triage; เปลี่ยน obsolete catalog/UI/synchronous-run assertions เป็น current contracts ไม่มีเพิ่ม skip/xfail หรือถอด test เพื่อให้ผ่าน มีการแทนที่ obsolete scenario titles จึงไม่อ้างว่า assertions ทุกบรรทัดเดิมยังอยู่
- Canvas pixel checks เพิ่มความเข้มกว่า attribute-only; ROI translation tolerance มาจากสอง CSS pointer endpoints/zoom และยังตรวจขนาดไม่เปลี่ยน ไม่ใช่ arbitrary tolerance
- Dataset source-missing test ยังคงตรวจ export error→row คงอยู่→refresh unavailable/export disabled→restore owned synthetic file→valid export; product Dataset/bulk-selection ไม่ถูกเปลี่ยน
- Mutation-style probe ถอด raw leaf extraction แล้ว prediction contract ล้มตามคาด; malformed/count mismatch/structured precedence/429 exhaustion/non429/cancellation อยู่ใน full backend suite

## Web Storage fix และ idempotency

`frontend/lib/job-navigation.ts` เก็บเพียง job IDs/acknowledgements ใน tab memory และลองเขียน browser storage แบบ optional ไม่มี OCR/GT/secret ใน hints และเรียกเฉพาะ client effect/event ไม่ใช่ SSR request state

`OCRJobRunner.tsx`:

1. GET case job จาก server ทุก mount; memory/browser hints ใช้ควบคุมการนำทางเท่านั้น
2. ก่อน POST เก็บ request key ใน ref; request failure ใช้ key เดิม retry ไม่สุ่ม key ใหม่เพราะ storage เขียนไม่ได้
3. API accepted job ถูก set ก่อน browser persistence; storage failure ไม่เปลี่ยน acceptance เป็น failure
4. explicit new run หลัง known terminal job ไม่ใช้ stale persisted key; failed retry ของ new run ยังใช้ pending key เดิม
5. completed/partial checks เป็น GET bounded6attempts/30s และ recheck ไม่ POST
6. refresh หลัง ambiguous acceptance ใช้ persisted server job ไม่ต้องมี browser key; server enqueue dedupe/idempotency/fencing ไม่เปลี่ยน

Coverage: local get/set throws, session get/set throws, methods ถูกปฏิเสธทั้ง session, window storage getters unavailable, storage เสียหลัง POSTเริ่มและยังเสียหลัง reload, completed/partial success, GT editing, back, refresh, manual read-only recheck และ ambiguous response retry/reload

ข้อจำกัด: ถ้า storage เสียและ reload จน tab memory หาย อาจตรวจผล/นำทางจาก terminal server jobอีกครั้งหนึ่ง แต่ไม่มี inference ใหม่หรือข้อมูลสูญหาย การซ่อน navigation ซ้ำไม่ใช่หลักฐาน exactly-once inference

## Memory audit

ไม่ได้รัน heavy resource experiment ซ้ำ: หลักฐานเดิม checksumตรง และมี headroom ต่ำเพียงพอที่จะปฏิเสธ capacity GO โดยไม่ต้องสร้างภาระเพิ่ม ไม่มี production resource/config change

| ช่วง/ตัวชี้วัด | ค่าที่มีหลักฐาน |
|---|---:|
| Backend cgroup limit | 512,000,000 bytes |
| sampled process RSS สูงสุด (oversize response) | 481,845,248 bytes |
| sampled cgroup สูงสุด (excessive geometry) | 511,963,136 bytes |
| sampled headroom ต่ำสุด | 36,864 bytes |
| cumulative memory.events max หลัง5phaseต่อเนื่อง | 1,039 |
| observed oom/oom_kill | 0/0 |
| kernel memory.peak หลัง replacement เท่านั้น | 233,033,728 bytes |

RSS คือ resident process memory; cgroup current รวมสมาชิก/anonymous/file cache/kernel accounting จึงหักRSSออกแล้วเรียกว่า file cacheไม่ได้ memory.events max คือ hit/pressure counter ไม่ใช่ OOM count; 50ms samples อาจพลาด peak สั้น VmHWM/countersสะสมข้าม5phase แต่ kernel peak หลัง container replacement เป็นคนละช่วง ไม่เอามาสรุปว่า peakทั้งงานลดลง

เส้นทาง allocation ที่ตรวจพบ:

- `model_gateway.py:327–336`: เก็บ decoded response ใน bytearray, extend ก่อนตรวจ64MiB limit และ `json.loads` materialize object tree ทั้งก้อน size limit ไม่ใช่ heap limit และหนึ่ง chunk อาจใหญ่กว่างบที่เหลือ
- `model_gateway.py:55,409`: raw-only extraction รักษา scalar/geometryก่อน drop transport; ขั้นตอนนี้เกิด **หลัง JSON parse** จึงไม่ป้องกันต้นทุน parse tensor เดิม
- `model_gateway.py:78,416`: recursive sanitizer สร้าง dict/list ใหม่; DET top-level/nested aliases อาจถูก copy ซ้ำ เพราะไม่มี memo ส่วน outer payload ยังอยู่ระหว่างสร้างผลลัพธ์
- `batch_gateway.py:34,67–81`: flat inputs, collected outputs, template และ owned deepcopy อยู่ร่วมกันช่วงส่งคืน slice แม้ไม่ deepcopy combined raw tensor ทั้งก้อนแล้ว
- `global_layout_service.py:315–332` และ `benchmark.py:115`: source image, bounded group crops, per-REC PNGs และ parsed responses อยู่ร่วมกัน; context managers ปิดภาพ แต่ Python allocator/RSS ไม่จำเป็นต้องคืน OSทันที
- ค่าปัจจุบัน tasks4/fields8 + response64MiB ไม่ใช่ memory reservation ข้ามrequest; workload admission/serialization envelope ยังไม่พิสูจน์

ยังไม่มี memory.stat breakdown/phase-level heap profiles จึงไม่ชี้สัดส่วน heap/cache/GC หรือ causal attribution ของแต่ละ phase ไม่อ้าง historical HTTP502 เกิดจาก OOM

Mitigation งานแยกที่วัดผลได้: จำกัด decoded chunk และ pre-append rejection, early Content-Length rejectionเป็นตัวช่วยไม่ใช่ security boundary, parse/retainเฉพาะallowlistแบบincremental, ลด alias/deepcopyที่พิสูจน์ว่าimmutable, ลด max response/tasks/fieldsตาม workloadจริง และวัด before/after ด้วย image/model/limitsเดิมหลายรอบพร้อม memory.stat/current/peak/events/latency/unique outputs ต้องกำหนด headroomและmax workloadก่อนอนุญาต release เช่นเป้าหมาย margin25%เป็น **ข้อเสนอ** ไม่ใช่ผลที่ผ่านแล้ว

## Jobs / GT / data integrity

- `ocr_jobs.py:133` lock case + lookup idempotency key + active-job dedupe; config snapshot ไม่อิง model editsหลัง enqueue
- `ocr_jobs.py:199,246` fence owner/status/expiry, advisory claim lock และ skip-locked; checkpoint transactionรวม parent IDs/counts; workerเก่าไม่สามารถ commit หลังเสียlease
- `global_layout_service.py:303–345` reuse parent/checkpointและข้าม persisted field IDs; upstream callsที่ยังไม่commitอาจซ้ำเมื่อ crash ไม่ใช่ exactly-once inference
- `ocr_jobs.py:307–334` countต้องครบก่อนterminal และ failed_units==totalเป็นfailed ไม่ใช่success; SQL failureไปlease recovery ไม่ appendใหม่โดยเดาcommit outcome
- Saved results APIเป็นread-only; empty200/failed fieldsไม่ทำให้navigateสำเร็จโดยไม่มีusable field; bounded errors/abort/403/deadlineมีbrowsertests
- หลักฐาน workerเดิม48unique outputs/32checkpoint IDs preserved checksumตรง ตรวจ harnessแล้ว แต่ไม่เรียกสิ่งนี้ว่าworker kill experimentใหม่ในauditรอบนี้; full backendใหม่ตรวจfencing/recovery/GT/missing sourceและPostgreSQL atomic claim
- Aggregate report ไม่เก็บ final per-field ID listครบให้ recount48และเทียบ32IDsโดยอิสระอีกครั้ง จึงยืนยันได้ถึงความสอดคล้องของharness/checksum/รายงาน ไม่ใช่การทำkill experimentซ้ำหรือรับรองexactly-onceupstream

## Requirement acceptance — local เท่านั้น

| REQ | ผล |
|---|---|
| 01 | view persistence/fit/zoom/reset/load recovery มีtests; storage blockedไม่ทำลายsaved GT |
| 02 | screen-space strokes ไม่เปลี่ยนsource ROI; geometry assertionsคงอยู่ |
| 03 | label hide/outlines remain ผ่านpixel checks; ไม่เพิ่ม requirement labels-without-outlines |
| 04 | selected/missingGT/error visual statesและtext indicatorsคงอยู่ |
| 05 | completed/partial→usable persisted results→GT; empty/errorboundedและstorage-negative tests |
| 06 | finished_at→updated_at fallback; terminal frozenทั้ง4status ไม่ใช้เวลาที่เปิดหน้า |
| 07 | missing GT/draft sync/explicit confirmation; ไม่แก้GTหรือmetric engine |
| 08 | local scroll/focus/38fields/resize/zoom มีbrowsercoverage |
| 09 | result dialog/GT/error/close/Escape/focus return ไม่รันinference |
| 10 | Thai combining marks/deletion/whitespace glyphsคงcharacter evidence; metric codepointsไม่เปลี่ยน |
| 11 | valid error-summary contractไม่reproduce duplicate full panels; per-event excerptsคงไว้ |
| 12 | OUT OF SCOPE |
| 13 | recovery correctnessผ่านlocal; resource capacityยังBLOCKED |
| 14 | Debug UI fail-closedจริง; backend authorizationยังBLOCKED ไม่เรียกการซ่อนUIว่าaccess control |

## Security / upload work แยก gate

[Security rollout](pr13-security-rollout.md) ครอบคลุม identity/issuer/audience/expiry, ownership migration/backfill/quarantine, ทุกIDในbulk/export, worker identity, debugRBAC, cache/CSRF/revocationและfail-closedrollback ก่อน implementต้องระบุtenant model, permissions matrixและlegacy ownership mappingที่ผู้รับผิดชอบอนุมัติ; cross-tenant401/403/404 testsต้องผ่านทุกread/write/download/job/admin endpoint

[Upload runbook](pr13-upload-recovery-runbook.md) ต้อง inventory originalsทั้งหมด, encrypted manifest+recovery key, restoreทุกhash/referenceในisolated target, write-freeze/final delta, durable destination/UID permissions, independent backupและrollback ห้ามเอา50samplesมาแทนinventory ห้ามmountทับsourceก่อนbackup ห้ามถือว่าrestoreเข้าephemeral containerเป็นdurability ไม่มีขั้นตอนproductionเหล่านี้ถูกexecuteในงานนี้

## Validation ใหม่

ผลด้านล่างบันทึกหลัง full browser run จบและตรวจ child exit code แล้ว; artifacts อยู่ `.runtime/final-independent/` ไม่เข้าGit

- Backend independent full run: **545 passed**,0failed/0skipped,124.39s,exit0 รวมPostgreSQL
- Original evidence hashes: **10/10 matched**; XMLเดิม545/0/0/0 และbrowser logเดิม188passed ยืนยันว่ามีหลักฐาน ไม่เรียกว่าfresh results
- Independent negative backend probes: **4passed**,0.61s; first attempt2setup errorsเพราะWindows temp ACL แก้เฉพาะbasetempเข้าworkspaceแล้วผ่าน ไม่แก้product
- Pre-fix GT storage read/write regressions: **2failedจริง**; raw browser probeเห็นSecurityErrorและไม่มีGT input
- First independent full browser: **186passed/2failed** จากtrace ENOENT เพราะparallel probeใช้outputdirectoryเดียวกัน ไม่ใช่green run; final suiteรันเดี่ยว
- First focused storage/navigation: **25passed/1failed** เพราะselectorชนNext route announcer แก้ให้scope OCR status regionและคงassertionเดิม
- Ruff app/tests: PASS; historical migration0010 I001ยังคงไม่แก้
- Final independent full Playwright: **206 passed**, 0 failed, 5.1m, child exit 0. Includes 29 job-result/storage tests (not a separate 29-test run). No concurrent Playwright process used this final output directory.
- TypeScript: PASS; ESLint: PASS; production build: PASS (final isolated E2E runner build).
- Fresh local PostgreSQL migration: clean database through 0011 to **0012_ocr_jobs**, 15 tables, no schema drift; temporary test database removed. No Production database access.
- Final diff/secret/link checks: PASS; private values and temporary evidence excluded from Git. Evidence remains under `.runtime/final-independent/`.

**Release gates:** authorization, durable uploads+verified recovery และresource envelopeยังไม่ผ่าน คงDraft PR ไม่merge/deploy แม้localtestsผ่านทั้งหมด
