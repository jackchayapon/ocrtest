# Independent engineering review — PR #13

> Final independent continuation: [ผล audit และ Web Storage regression fix รอบล่าสุด](pr13-final-independent-audit.md). ตัวเลข188 browser testsด้านล่างเป็นผล remediationก่อนหน้า ไม่ใช่ผลรอบใหม่ คงProduction NO-GOและREQ-12 OUT OF SCOPE

> Remediation ต่อเนื่อง: ดู [ผลตรวจล่าสุด](pr13-remediation.md), [triage ทุก 55 backend/34 browser failures](pr13-failure-triage.md) และ [แผน authorization](pr13-security-rollout.md) ก่อนใช้ผล historical ด้านล่าง REQ03 ไม่รวม requirement labels-without-outlines; Debug diagnostics ถูกปิดแทน toggle เดิม คำตัดสิน Production ยังคง NO-GO

**ผลสุดท้าย remediation:** backend **545/545**, full Playwright **188/188**, runner exit code **0 ทั้งคู่**, ไม่ skip; PostgreSQL clean→0011→0012/head และ no-drift ผ่าน TypeScript/ESLint/build ผ่าน Ruff app/tests ผ่าน แต่ทั้ง backend ยังมี baseline I001 หนึ่งจุดใน migration0010 ไม่มีการแก้ migration เก่า REQ03 ตรวจ pixels ของ label/outline, REQ06 ใช้ persisted finish, REQ11 ไม่พบ duplicated full panels ด้วย contract จริง; REQ13 recovery ผ่านใน local แต่ memory headroom ต่ำยังเป็น blocker ไม่ใช่ production capacity proof ไม่มีการอ่าน private production data/uploads

วันที่ 8 พฤศจิกายน 2569 · **คำตัดสิน production: NO-GO** · คง Draft PR

## 1. ขอบเขตและหลักฐาน

เริ่มตรวจ branch `fix/ocr-workflow-regression-audit` ที่ HEAD `83ede9e735d530648263ceb68f5fc679e3fb87b3` เทียบ main `695bf4b0f3355653ea4c82102e6586debaac9c2b` ยืนยัน GitHub REST: Draft=true, merged=false, Preview check success ไม่มี backend regression CI ที่ตรวจพบใน checks นี้

ตรวจ diff เดิม 27 files รวม callers ของ job creation/results, worker, batch splitting, normalization, storage, UI และ deployment configs ไม่ถือรายงานเดิมเป็นผลทดสอบใหม่ ไม่อ่าน/export เอกสาร production, ไม่แก้ DB/secret, ไม่ restart/merge/deploy ผล live CDGS/494-unit เป็นหลักฐานเดิมเท่านั้น
ลิงก์วิดีโอการประชุม fetch ไม่สำเร็จ (cache miss) จึงใช้ REQ ที่ผู้ใช้ระบุ ไม่อ้างว่าได้ดูวิดีโอ

## 2. ข้อบกพร่องที่พิสูจน์และแก้ในรีวิว

| ระดับ | ข้อค้นพบที่ HEAD เดิม | การแก้/หลักฐานใหม่ |
|---|---|---|
| P1 | Terminal job + Results200 ว่างหยุดหลังอ่านครั้งเดียว แม้ผลจะพร้อมภายหลัง | `OCRJobRunner.tsx:47–74`: recheck ทุก5วินาที ไม่เกิน6attempts/30วินาทีต่อรอบ แล้วหยุดพร้อม manual read-only recheck |
| P1 | Results503 อ่านซ้ำไม่สิ้นสุด (reproduction พบ9readsหลังเลื่อน browser clock) และ fetch ค้างไม่มี deadline | ใช้ AbortController + deadline; permanent4xx ยกเว้น408/429หยุดทันที; cleanup abort เมื่อ unmount; `api.ts:120` รับ signal แยกจาก shared read coordinator |
| P1 | Parent success แต่ทุก field error สามารถถูกนับ usable ด้วย OR เดิม | เมื่อมี field ใช้ field status จริง; test all-failed ไม่ navigate และหมด budget ตามกำหนด |
| P2 | ปุ่ม Run OCR หลัง terminal ไม่แยกความหมายจากอ่านผลเดิม | เปลี่ยนเป็น “รัน OCR ใหม่ (ประมวลผลซ้ำ)” และแยก “ตรวจผลอีกครั้ง (ไม่รัน OCR)” ไม่มี POST เมื่อ recheck |
| P2 | Mark navigated ก่อน callback ทำให้ synchronous navigation failure ไม่มีทาง retry จากปุ่ม | Mark หลัง callback คืนค่า; manual recheck reset guard; ผลและ Job ID ยังอยู่ ไม่อ้างว่าจับ async router failure ได้ทุกชนิด |

Regression ใหม่ `frontend/tests/job-result-verification.spec.ts`: empty completed/partial→later usable, persistent503, parent-success/all-fields-error,403, pending fetchจนdeadline, manual recheck และ GT data loading failure→reload/back โดยยืนยัน POST=0 และ Job ID ไม่หาย ไม่แก้ backend job status ให้เป็น success เอง

## 3. Requirement matrix

VERIFIED หมายถึงขอบเขต local code/tests ที่ระบุ ไม่ใช่ production acceptance

| REQ | สถานะ | ตำแหน่ง/ผลตรวจ |
|---|---|---|
| 01 fit/zoom/pan | VERIFIED ใน flows ที่ทดสอบ | `DocumentViewer.tsx:103–171,211`; `SourceCropPreview.tsx:8–36`: identityใช้source/dimensions, resizeไม่รีเซ็ต manual scale; mobile/PDF crop tests ผ่าน การสลับ source ใช้ fit ไม่ reuse viewผิดภาพ |
| 02 thin borders | VERIFIED (code + browser regressions) | `DocumentViewer.tsx:612,617`, `TestRegionLayer.tsx:79`:1.25/2/1.5px,ไม่เปลี่ยนROI; ไม่ได้วัด pixel screenshot ทุก zoom |
| 03 independent controls | PARTIAL | `DocumentViewer.tsx:613,618`: label toggleแยกได้ แต่ซ่อน all-fields ยังซ่อน labels ของ non-selected ด้วย (`showAllFields && showFieldLabels`); ถ้าต้องการlabelsโดยไม่มีoutlines ยังไม่ครบ ไม่ถือ data-attribute assertion พิสูจน์ canvas ทุกชุด |
| 04 selected field | VERIFIED | `DocumentViewer.tsx:610–618`, selection tests:violet/fill; missingGTแดง,OCRerroramber/dashedและlabel; selectedสีมีpriorityโดยตั้งใจ |
| 05 terminal→GT | VERIFIED สำหรับ tested branches หลังแก้ | `OCRJobRunner.tsx:47–74`, `GlobalWorkspace.tsx:57`:boundedresults,partialwarning,failed/cancelled100%ไม่navigate, retainedID/recheck; GTโหลด503แล้วrefresh/backไม่ส่งOCR |
| 06 progress/readability | PARTIAL | `OCRJobRunner.tsx:83–100`:units/status/checkpointชัด แต่ elapsedของงานเก่าคำนวณจากbrowser clockไม่ใช่finished_at จึงไม่ใช่ระยะเวลาจบงานที่แม่นยำเมื่อเปิดใหม่ (P2เดิม) |
| 07 missingGT | VERIFIED | `GlobalGroundTruthForm.tsx:29`, workflow-audit test:computed redborder,warningคงพื้นที่,กรอกแล้วซ่อน,ไม่กระโดดpreview |
| 08 bidirectional focus | VERIFIED | `GlobalWorkspace.tsx:41`, `GlobalGroundTruthForm.tsx:10`:38fields,immutableID,local scroll,focus preventScroll,caret/zoom ไม่ถูกreset |
| 09 result modal | VERIFIED | `GlobalFieldEvaluation.tsx:67`, `PipelineResultPreview.tsx:17–43`:Field/Whole,GT identity,Escape/focusreturn,ไม่เรียกOCR; mobile mock browserผ่าน |
| 10 Thai highlighting | VERIFIED ใน fixture coverage | `InteractiveErrorText.tsx:12`, `highlight-units.spec.ts`:combining marks/deletions/English/numbers retained; displayglyphไม่แก้ metrics/normalization |
| 11 duplicate error details | PARTIAL / NOT REPRODUCED | `CharacterErrorSummary.tsx`, `GlobalFieldEvaluation.tsx`:summary/on-demand detail คงอยู่; ไม่มี exact meeting repro จึงไม่ประกาศปัญหานี้แก้ครบ |
| 12 | OUT OF SCOPE | ไม่เปลี่ยน confidence calibration/threshold logic |
| 13 durability/recovery | PARTIAL | `ocr_jobs.py:133,199,252,307`:DBlocks/lease/fence/checkpointsผ่านlocal testsและPG; original uploadsยังephemeral, heavy494ไม่ได้รันใหม่ |
| 14 debug authorization | BLOCKED | `SafeDebugPanel.tsx:5–10`, `api/dependencies.py`:allowlistไม่ใช่authorization;ไม่มีlogin/roles ไม่สามารถรับรอง internal-only |

## 4. DET/REC และ HTTP429

`model_gateway.py:55–76,405–419`:ก่อนหน้า unconditional raw_output removal เห็นได้จากbase diff; synthetic raw-only DET/REC testsพิสูจน์ fallbackเก็บpolys/scores/textและทิ้งinput_img/path ไม่ใช้เพียงHTTP200ตัดสินsuccess Structured aliasesเป็นauthoritative:ถ้า malformed ไม่ใช้rawfallbackกลบข้อผิดพลาด

`batch_gateway.py:33–95` แบ่งตามurl+query, input order/owner, count และbatchrequestIDs; `benchmark.py:89–139` ตรวจkind/version,count,polygons≤1000,scorelengthและquadก่อนREC; `normalizers.py:189` rejects missing/non-string/excessive text. `image_service.py:105` จำกัดgeometry/image boundsก่อนperspective transform Model routingไม่มีdiff:BenchmarkDET6/REC5ไม่เพิ่มmodel/engine; dynamicใช้registered path;ไม่แก้weight/GT/CER/WER/Datasetlabel

ทดสอบเพิ่ม9cases ใน `backend/tests/test_gateway_retry_review.py`:HTTP-date/invalid/extremeRetry-After,4concurrent429แต่ละrequestไม่เกิน3attempts,jitterbounds,cancelระหว่างbackoff,timeoutหลังretry,422/500/503ไม่retry,structuredprecedenceและoversizedbody; รวมกับ14compatibility testsเดิมที่รันใหม่ผ่าน

**ข้อควรระวัง:** `model_gateway.py:232–244` 30วินาทีเป็น **retry admission budget** ไม่ใช่absolute deadlineของinferenceทั้งหมด:attemptที่เริ่มแล้วใช้timeoutเดิมได้ ห้ามเรียกว่าtotal request≤30s การretry429ไม่สร้างPipelineRunใหม่; interruptedHTTPก่อนcheckpointอาจถูกinferซ้ำได้ตาม at-least-once ไม่ใช่exactly-once upstream

## 5. Job ownership, duplicate submissions และ navigation

- `pending.current`กันdouble-clickในinstance; browserเก็บidempotency keyจนรับ202 และbackendrowlock/active-jobguardป้องกันsimultaneousactivejobs; samekeyหลังcompletedคืนjobเดิม (tests/test_ocr_jobs.py:90,146)
- pipeline selectionเปลี่ยนระหว่างactiveถูก409 ไม่เลี่ยงguard; keyผูกorderedselection ดังนั้นเปลี่ยนลำดับ/selectionหลังjobจบเป็นexplicit new intent ไม่ถือexactly-onceข้ามทุกtabหลังterminal
- Refresh/backไม่มีimplicitPOST, lost202ใช้keyเดิม (existingocr-jobs browsertestsรันใหม่); multipleconsumerPGclaim/fence/recoveryรันจริงในlocal DB
- `router.push`เป็นvoid ไม่มีawaitable success acknowledgement. guardตอนcallbackไม่ใช่ยืนยันrouteโหลดสำเร็จ มีmanualresultslink/recheckและsessionackเมื่อGTโหลดแล้ว ทดสอบGTAPI503→reloadแล้วbackสำเร็จ; **router internals throw/failed RSC transportทุกแบบไม่ได้execute** จึงไม่อ้างcoverageครบ
- GT acknowledgementยังพิจารณา `hasRuns` ของcase ไม่เทียบrun_idsของjobทุกตัว (GlobalWorkspace:57):ฐานข้อมูลprimaryปกติcommitก่อนterminal แต่ถ้าใช้stale/replicatedreadsต้องเพิ่มmatching-job acknowledgement testก่อนเปิด topologyนั้น

## 6. Independent test evidence

หลักฐานใหม่อยู่ `.runtime/pr13-review/` (ignored ไม่commit private/runtime artifacts)

- Full backend535cases: **480passed/55failed/0skipped** (99.04s) รวม local PostgreSQL atomic claim, upgrade0011→0012 และschema check; failure IDsเท่ากับbaseline55 ไม่มีnew IDs
- จากนั้นเพิ่มreview-only9backendtestsและรัน: **9/9passed** ไม่อ้างว่าfull544ถูกรันพร้อมกัน; application backendไม่มีการแก้ในreviewนี้
- Focused real-local-API + browser set รอบสุดท้าย: **39/39passed (53.1s)** รวม7new result-verification/GT-loading cases และ32existingcases มีlocalPostgreSQL/mockGateway;ไม่ใช่productiontest
- Typecheck, ESLint, production buildผ่าน; changed Python Ruffผ่าน ไม่อ้าง whole-repoRuffไม่มีbaselineissues
- Artifact XMLเดิมยืนยัน466/55baseline และ480/55PR; logเดิมPlaywright128/34baseline,137/34PR มี34failuretitlesชุดเดียวกัน นี่เป็นการตรวจartifact **ไม่ใช่ fullPlaywright rerun** และmatchingIDsไม่พิสูจน์ว่าเหตุ/ผลกระทบของทุกfailureเหมือนกัน
- ตรวจtestdiffไม่พบskip/deleteเพื่อให้ผ่าน; Reset assertionเปลี่ยนจากห้ามเป็นrequireให้ตรงREQ01พร้อมยังห้ามROIedit/delete; ใหม่ทดสอบstatus/POST count/retainedID/stop/recovery ไม่เพียงsnapshot
- FullPlaywright171ยังไม่ได้รันใหม่ในการreviewนี้ ใช้affectedjob/UIชุดครบแทน เนื่องจากknown34failures; ก่อนGOต้องtriage/waive release-criticalfailuresและรันfullacceptanceกับbaselineที่ดูแลแล้ว ไม่ relabelว่าgreen
- Initialreviewharnessสะดุดเพราะpartialnavigateเร็วกว่าprogress assertion; testใหม่4failเพราะlocatorรวมNext route-announcer จึงscope alertให้OCRregion; GT-failurefixtureปรับexpectedtextให้ตรงexistingThaierror-sanitizationพร้อมassertcaseReads=2 ไม่ลดexpectedbehavior

## 7. Baseline failures ที่ยังเป็นความเสี่ยง

55backend failuresไม่ได้แปลว่าallharmless:มีlegacy pipeline seed404/None, GT sync/evaluation, ROI, Dataset, privacy/persistence tests. ตรวจ3Benchmarkfailuresซ้ำตรงmissinglegacyconfig แต่ต้องแยกobsoletefixturesออกจากจริงทีละcase ไม่ลบtests
34browserfailuresครอบคลุมglobalGT,PDF,comparison,Dataset,history/settings ไม่ใช่แค่cosmetic จึงยังไม่ผ่านrelease gateแม้deltaไม่มีfailureIDใหม่ ต้องมีowner/เหตุ/หลักฐานทดแทน/waiverแต่ละrelease-criticalflow

## 8. Memory และ recovery

ตรวจartifact494outputs/971.57s/RSS309313536/cgroup477556736/limit512000000:headroom **34443264bytes≈34.44MB (6.73%)** เป็นsingle synthetic workload ไม่ใช่productioncapacity; ไม่รันheavy workloadหรือCDGSloadใหม่
`_send`เก็บbytearrayและJSONobjectก่อนstripraw;64MBresponsecapไม่จำกัดPythonheap amplification หรือmanysmallnumbers/tensorsที่parseแล้ว; DET≤1000ยังอาจสร้างหลายRECbatch; originalimage+หลายcrop+ownerdeepcopiesยังอยู่ในmemoryพร้อมกันได้
Limitedtask/field/batch admissionและquad boundsช่วยแต่ไม่ใช่memoryproof เหตุOOMเก่าและworkerexitยังไม่ยืนยัน ควรวัดadversarialgeometry/largeREC/concurrency envelopeบนisolatedresourceเท่าจริง, cgroup memory.events/peak+RSS, repeatedsoakก่อนGO
PG fencingป้องกันstalecommit;ไม่ป้องกันupstreaminferenceซ้ำของunitที่ยังไม่checkpoint; missingoriginalให้failedพร้อมsavedpartial ไม่มีfabrication

## 9. Security และ data integrity

- **P0 deployment data-loss risk (pre-existing):**ไม่มีverifieddurableuploads/backup ห้ามreplacecontainerจากหลักฐาน50samplesเพียงอย่างเดียว ไม่อ้างข้อมูลสูญหายจริงแล้ว
- **P1 pre-existing privacy/access-control gap:** `main.py:126–133`, dependenciesและdocuments/jobs APIไม่มีuser authorization;CORSไม่ใช่authentication ใครเข้าถึงAPIได้อาจอ่านหรือแก้ข้อมูลตามexistingroutes ไม่ทดลองกับprivateproductiondata
- SafeDebugPanelเพิ่มvisibilityของexistingIDs/codes แต่ไม่มีrawpayload/keyviewerและReactescapeข้อความ ไม่ใช่newcross-usersearch อย่างไรก็ดีinternal-onlyREQ14ยังBLOCKED
- LocalStorageService `_path` resolve+parentcheckป้องกันtraversalออกroot;UUIDgeneratedkeys, no unsafeHTMLเพิ่ม. SanitizedfieldlogจำกัดupstreamID; body/OCR/GT/Authorizationไม่ถูกเพิ่มในlogs
- Secret scanตรวจexactprivatevaluesแบบไม่แสดงค่า, .env/runtimeไม่tracked; ไม่อ้างว่าครอบคลุมsecretที่ไม่รู้จักทั้งหมด
- ไม่มีmigrationใหม่,modelconfig/env/deployconfig/metrics/Datasetsemanticschange; productionไม่ถูกแก้จากreview

## 10. Upload preservation และ release prerequisites

Runbookที่เตรียม: [production uploads recovery](pr13-upload-recovery-runbook.md) รวมinventory/reconciliation, encryptedmanifest,Windowskeyrecovery,localdrill,writefreeze,hashverification,rollbackและkeyrevocation ไม่executeexportในงานนี้
คืนไฟล์เข้าephemeralcontainerใหม่ไม่ใช่durabilityถาวร DBbackupแทนuploadsไม่ได้ ต้องอนุมัติdurabletarget/backupและพิสูจน์restoreก่อนrelease

ก่อนเปลี่ยนเป็นGO: (1) sourcepreservation+durabilitygateผ่าน (2) internal-onlypolicyมีauthboundaryจริงหรือปรับscopeโดยownerอย่างชัดเจน (3) triage55/34failuresและfullcriticalacceptance (4) memoryenvelope/rollbackพร้อม (5) reviewข้อPARTIALREQ03/06/11และacknowledgementlimitation

## 11. คำตัดสิน

**NO-GO สำหรับ production; Draft PR พร้อมให้รีวิวfixต่อ** สองP1ที่ผู้ใช้ระบุแก้และมีtestsแล้ว แต่ไม่เปลี่ยนสถานะstorage/security/baselinefailuresให้ผ่านโดยปริยาย ไม่มีmerge/deploy/restart/productionexport และไม่อ้างPR13verifiedบนproduction
