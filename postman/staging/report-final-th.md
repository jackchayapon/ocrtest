# ผลแก้ไข OCR resource management — candidate release

สถานะ: **FIXED WITH RESIDUAL RISK / PRODUCTION RELEASE BLOCKED** ไม่ได้ประกาศว่าปัญหา422/502เดิมได้รับการแก้ที่productionแล้ว

## สิ่งที่แก้จริง

- Fixed worker pool + semaphore จำกัด adapter tasks ข้าม fields (default2) และ field preparation group(default2) แยกจาก Gateway batch cap30
- ตัด leaf raw_output/extra transport archives ก่อน recursive redaction และไม่ deepcopy combined response ทั้งชุดต่อ owner
- รักษา OCR text, polygons, confidence, result order/field identity, model_selection, Request IDs, metrics inputs และ compact provenance ไม่มี model/weight fallback หรือ retry422
- แยก UPSTREAM_MODEL_ERROR จาก request validation พร้อม safe error codes/types, selected query identifiers, batch count, inflight count และ Linux memory readings
- Frontend อธิบาย model-worker failure และ partial field successes เป็นภาษาไทย พร้อมชี้ให้ใช้ Gateway Request ID
- แก้ test assertions ของ migration head ที่ค้างอยู่0009/0010 ให้ตรวจ0011_gt_prefill ไม่แก้หรือลบ historical migrations

## Before / After — workloadเดิม14stage/profile

| รายการ | Before | Candidate |
|---|---:|---:|
| OCR HTTP runsสำเร็จ | 18/18 | 18/18 |
| Gateway batch calls | 60 | 132 |
| Max Gateway inflight | 4 | 2 |
| Stage E sized peak RSS | 540.3 MB | 281.4 MB |
| Stage E sized peak cgroup | 511.9 MB | 465.6 MB |
| Stage E sized P95 (n=1) | 4994.14 ms | 4974.58 ms |
| Stage E compact P95 (n=1) | 1670.48 ms | 4539.13 ms |
| OCR502 / process crash / OOM kill | 0 | 0 |

Gateway callsเพิ่มเพราะงานเล็กลงและรวมbatchได้น้อยลง เป็นtradeoffจริง ไม่อ้างว่าเร็วขึ้นทุกกรณี Model inputs/assetSHAและจำนวนpipelines/fields/HTTPconcurrencyตรงกันทุกstage ตรวจ74 field predictionsสำเร็จตรงsynthetictextและglobal-field mapping ไม่มีduplicate field indices

Candidate cgroupครั้งแรกมีinactive file cacheราว205MB จึงไม่เท่ากับRSSหรือanonymous heap Raw cgroup peak465.6MBยังสูงกว่าเป้าหมาย400MB ต้องไม่ปิดบัง จุดเดียวนี้ยังไม่พอรับรองcloudheadroom

เมื่อทดสอบ sized E ซ้ำกับfinal sourceหลังเพิ่มobservability: RSS262.5MB/cgroup234.9MB, inflight2, runผ่าน ไม่เกิด502/OOM ความแตกต่างด้านcache/warmup/accountingทำให้ไม่ควรเลือกเฉพาะค่าที่ต่ำที่สุดเพื่อประกาศว่าแก้productionสำเร็จ

## Functional / real Gateway

- Sequential CDGS7คู่model/versionผ่านHTTP200อีกครั้ง Newman preflight+baseline10/10 requests,20/20assertions
- Corrected local candidateต่อCDGSจริง โดยDB/storageแยก: Auto ROI1region, manual crop483x62, DET6/REC5สำเร็จ, GTยืนยันแล้ว CER0/WER0/ExactMatchtrue, เปิดผลซ้ำ/History/Matrix/Analyticsผ่าน, evaluation ZIP5entriesเปิดได้ และPDF2pages/previewpage2ผ่าน
- Helperเคยส่งevaluate mode=per_fieldพร้อมrequire_complete_gt ทำให้API422ตามcontract จากนั้นแก้เป็นmode=autoโดยไม่ยิงinferenceซ้ำ เหตุการณ์นี้ไม่ใช่CDGS422
- ไม่มีการทำreal concurrent loadบนCDGS เพราะยังไม่ยืนยันoperatorpermission ผลmockไม่ใช้รับรองmodel-worker concurrency

## Persistence / rollback

ทดสอบเฉพาะlocal: backup/restore18syntheticuploadsพร้อมSHA256manifestตรงกัน แล้วrollbackกลับsourceproduction67df434และforwardกลับfinalcandidate โดยใช้DB/storageเดิม ค่าdigestของsavedcaseและimageไม่เปลี่ยน ถือเป็นlocalcompatibility/restoreproof ไม่ใช่productionbackup/PITRverification

Alembic isolated PostgreSQL:0011_gt_prefill(head), no schema drift ไม่มี migration ใหม่ ไม่มีproductionDBwritesหรือการลบHistory

## Release gate

- Railwayปฏิเสธสร้างisolatedprojectด้วยFreeplanresourceprovisionlimit แม้อนุมัติtemporaryusageแล้ว ยังไม่มีสิทธิ์upgradeแพ็กเกจ จึงไม่สร้างstagingหรือupgradeเอง
- Renderauthและdurable-storagecredentialsไม่พร้อม เตรียมrender.yamlแล้ว แต่ยังไม่deploy ไม่ใช้RenderFreeephemeralfilesystemอ้างว่าrestartpersistenceผ่าน
- ProductionคงRailwaydeployment432a98fb-8c9e-4fa9-bdb3-2e6e4cbf66cd/commit67df434…; Vercelยังใช้Railway ไม่มีcutoverหรือproductionsecretchanges
- Historical422internalreason/502exitreasonยังUNCONFIRMED ความเสี่ยงmemorypressureยืนยันได้เฉพาะworkloadจำลองที่วัด
- ผลfullregressionและPR/commitสุดท้ายดู [release validation](../../docs/production-release-validation.md)

## Required next authorization / access

ต้องมีทางสร้างisolatedcloudcandidateได้จริง เช่นอนุมัติแพ็กเกจRailwayที่แก้resourcequota พร้อมแผนหยุดstaging และdurablestorageที่restore-tested หรือเปิดRenderaccountพร้อมstorageที่ผ่านเกณฑ์ ก่อนปล่อยproduction ไม่จำเป็นต้องส่งsecretsผ่านแชต

ดู [results-final.json](results-final.json), [root cause](../../docs/ocr-performance-root-cause.md) และ [rollback/cutover](../../docs/railway-render-migration.md) สำหรับรายละเอียดและข้อจำกัด

## ผล regression สุดท้าย

Backend รวม PostgreSQL: 436 ผ่าน / 55 ไม่ผ่าน (baseline 425/59), ไม่มี failure ใหม่ และแก้ stale head assertions ได้ 4 รายการ Playwright ครบ 157: 123 ผ่าน / 34 ไม่ผ่าน (baseline 117/35 จาก 152 tests), ไม่มี failure IDs ใหม่ ทั้ง 5 tests ใหม่ผ่าน ไม่อ้างว่าชุดทดสอบทั้งหมดผ่าน TypeScript/ESLint/build และ Ruff เฉพาะไฟล์ที่เปลี่ยนผ่าน; Ruff ทั้ง repo มี 8 import-order findings เดิม

Browser ที่ต่อ CDGS จริงผ่าน OCR, ซิงก์ GT, Confirm, CER/WER/Exact Match, reload, History และ Comparison หลังแก้ GT ฝั่งเดียว ไม่มี console/API errors การรัน backend ซ้ำครั้งแรกติด permission ของ pytest temp แล้วรันใหม่บน temp แยกสำเร็จ ผลโหลดจำลองเก็บก่อนเพิ่มการปกปิด secret ใน error code/type ขั้นสุดท้าย โดยไม่เปลี่ยนการทำ OCR

สถานะ release: NO-GO; เตรียม Draft PR เท่านั้น ยังไม่ merge/deploy และ production เดิมยังอยู่ Railway ปิดเฉพาะ local diagnostic containers/process หลังเก็บหลักฐาน โดยเก็บ volumes ไว้
