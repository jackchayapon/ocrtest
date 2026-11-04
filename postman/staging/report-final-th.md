# ผลแก้ไข OCR resource management — candidate release

สถานะล่าสุด: **RELEASED — GO WITH DOCUMENTED RESIDUAL RISK** วันที่5พฤศจิกายน2569 รายละเอียดด้านล่างเรียงตามขั้นตอนและเก็บหลักฐานPRรุ่นแรกไว้ ไม่ได้อ้างว่าปัญหา422/502ย้อนหลังถูกแก้ถาวร

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

## Candidate สุดท้าย — 5 พฤศจิกายน 2569

เลือกค่า tasks4 / fields8 / batch4 หลังเทียบ2/4/4,4/8/4,8/8/4: ค่า4/8/4 ช้ากว่า8/8/4เล็กน้อยแต่ Gateway inflight ใน30x12ต่ำกว่า A–Gสำเร็จ18/18 ใช้64calls เทียบ132ของPRแรกและ60baseline Sized E3766.94ms/RSS324.8MB/cgroup284.4MB

30Fields×12Pipelines จากimageสุดท้ายผ่าน3รอบ รอบละ360/360ผลและ12/12pipelines ข้อมูลconfidence/trace360รายการ, DET/REC geometry300รายการอยู่ในROI (recognition-only60รายการไม่สร้างpolygonปลอม) ทั้ง360recordsบันทึกครบ ไม่มีซ้ำ Wall48.058/48.796/47.644วินาที รอบละ195calls PeakRSS315.2MB/cgroup340.4MB ไม่มี502/OOM/restart แยกฉีดfailureได้300success+60expected errorsโดยไม่สูญเสียrecords

Source productionเดิม67df434ในlocalcontrol30x12เดียวกันเกิด502และDockerOOMKilled=true/exit137ที่cgroup512MB นี่ไม่ใช่การพิสูจน์สาเหตุ502ย้อนหลังบนRailwayจริง

เวลาใหม่เก็บwall_clock_v1: processing_time_ms=wall_time_ms เป็นช่วงตั้งแต่fieldแรกถึงfieldสุดท้ายของpipelineรวมเวลารอคิวระหว่างกลุ่ม total_field_compute_msเป็นผลรวมเวลาfields และrun_wall_time_msเป็นเวลารวมก่อนDBsave/HTTPserialization ไม่เปลี่ยนค่าประวัติเดิม Gatewaydurationใช้attributionเดิม SummaryHistoryไม่โหลดrawprovenanceเพิ่ม

Backend447ผ่าน/55failureเดิม ไม่มีfailureใหม่ CDGS7คู่โมเดลผ่าน10HTTP/20assertionsจริง Browsercandidateต่อCDGSผ่านAuto+ManualROI,OCR2fields,GT,CER/WER0,ExactMatchtrue,wall805msกับcompute1608ms,refresh,History,Detail,Comparison,ZIP/Excel/PDF ไม่พบconsole/APIerrors DatasetPNG2ภาพbytesตรงcanonicalcropและlabelเป็นconfirmedThaiGTเท่านั้น rollback/forwardlocalรักษาเคสและไฟล์ครบ

คำสั่งล่าสุดยอมรับความเสี่ยงuploadsแบบephemeral และอนุญาตใช้localstagingตามด้วยproductioncanary ไม่ซื้อแพ็กเกจ ไม่mountvolume ไม่ลบrecords รอผลPlaywrightครบและproviderreleaseก่อนเปลี่ยนสถานะเป็นreleased

## Release gate ก่อน Merge

Playwrightครบ160:126ผ่าน/34failureเดิม ไม่พบfailureIDsใหม่ ทั้ง3timingtestsและGTbrowser2casesผ่าน รวมถึงDatasetpagination200รายการทั้ง2viewports Backend447/55เดิม ไม่มีregressionใหม่ TypeScript/ESLint/buildผ่าน Ruffไฟล์ที่เปลี่ยนผ่าน Alembic0011/no drift ไม่มีmigrationใหม่

Decision: GO WITH DOCUMENTED RESIDUAL RISK สำหรับworkloadที่ระบุ รอGitHubchecks/auto-deploy/canaryจริง ความเสี่ยงhistorical422/502ยังไม่ยืนยัน uploadsยังephemeralตามที่ผู้ใช้ยอมรับ ไม่ถือว่าbackupหรือrestartdurabilityผ่าน

## Production release สุดท้าย

PR8 merged b28f5d8193be9549e01b1aff9d6cc74809ef9144 และfollow-upDatasetPR9 merged a4dfb464dbaf2d3844035bef52a1ccb3c3d6bc39 Railwaydeployment471f2fc9-a4cc-4ded-b771-012fc9cf9c2a SUCCESS ใช้a4dfb46 Vercelproductiondpl_43zry3Abjxxx3nbX6QjXDGLRUvW2 READY ใช้b28f5d8 โดยfrontendtreeเหมือนa4dfb46 จึงไม่deployfrontendซ้ำสำหรับbackend-onlyfix APIยังชี้Railwayเดิม ไม่ย้ายRender

Backend449/55failureเดิม ไม่มีfailureใหม่ FullPlaywright126/34เดิมและDatasetUI4/4ผ่าน Post-followup30x12ผ่าน3รอบ360/360,195calls,47.529/47.789/47.052วินาที PeakRSS313.8MB/cgroup289.5MB ผลcandidateก่อนหน้ายังเก็บcgroup340.4MBไว้ ไม่เลือกซ่อนค่าที่สูงกว่า

Canaryproductionรุ่นสุดท้ายยิงOCRPOSTเดียวกับAuto+Manual2fields ได้successทั้งคู่ confidenceจริง0.996521/0.981628 CER/WER0 ExactMatchtrue wall3345ms/compute6690ms/run5121ms GTconfirm-refresh-History-Detail-Comparison-PDFpage2ผ่าน ZIP/Excel1sheetเปิดได้ ปุ่มexportExcelและDatasetZIPบนUIทำงาน PNGdataset2ภาพpixelsตรงต้นฉบับROIและbyteshashตรงinferencecrop labelเป็นconfirmedThaiGT ไม่ใช่prediction/metrics หน้าเว็บ9เส้นทางHTTP200ไม่มีJSerror/API5xx โดยErrorAnalysisกรองเคสcanary

Datasetlist50samplesproduction200ใน2217.77ms หลังแก้readpath localcontrol352->6queries/1,072,484->20,415estimatedDBbytes responseเท่าเดิม ทุกoriginalPK149documents/115cases/564runsยังอยู่ เพิ่มเฉพาะcanary4documents/2cases/2runs รวม153/117/566 Alembic0011ไม่migrate ไม่มีการลบ/รีเซ็ตข้อมูลหรือแก้secret Logsไม่มีGatewayerror/5xx/OOM/unexpectedrestart มีhistoricalcrop404และclientcancel499ตามที่บันทึกไว้ memoryplatformช่วง1ชั่วโมง/30วินาทีmax0.32043008GBไม่ใช่instantaneouspeakของcanary

Decision RELEASED—GO WITH DOCUMENTED RESIDUAL RISK: uploadsยังephemeralและoldmissingfilesไม่ฟื้นจากDB, historical422/502ยังไม่ทราบเหตุยืนยัน, all-historyErrorAnalysisยังช้าเกิน45วินาที (scoped200), baselinefailuresและRuff8findingsเดิมยังอยู่ และไม่รับรองsustainedCDGSconcurrency ไม่ซื้อแพ็กเกจ/volume/บริการใหม่ ไม่claimdurability ปิดเฉพาะlocaltestprocesses/containersและเก็บหลักฐานไว้
