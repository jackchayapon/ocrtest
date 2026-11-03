# CDGS Gateway — ตรวจสัญญา API และเตรียม PR (2026-11-03)

## เส้นทางและบริการที่พิสูจน์แล้ว

Base API path จริงคือ /paddle/api/v1 บน https://websolution.cdgs.co.th
DNS/TLS/Bearer authentication ผ่าน ไม่มีการตาม redirect หรือส่ง key ไป host อื่น
Health/readiness ตอบ200; OpenAPI และ Swagger ที่ตรวจพบยังตอบ404
ลิงก์ docs ที่ Gateway ส่งกลับก็ไม่เปิดใช้งาน จึงไม่เดา endpoint ที่ยังไม่มีหลักฐาน

| บริการ | Endpoint ที่ตรวจจาก Gateway จริง | ผล / การใช้งานในแอป |
|---|---|---|
| REC | POST /paddle/api/v1/text-recognition-batches?version=5&model=baseline | 200; DynamicRecognitionAdapter, DET→REC และ GT prefill |
| DET | POST /paddle/api/v1/text-detection-batches?version=6 | 200; DynamicDetectionRecognitionAdapter/Benchmark และ GT prefill |
| LAYOUT-PIPELINE | POST /paddle/api/v1/document-layouts | 200; AutoROIService |
| LAYOUT leaf | ยังไม่ทราบ endpoint ที่ยืนยันได้ | readiness: layout-model / leaf-layout ready; ไม่มี direct adapter |
| TABLE-v2 | ยังไม่ทราบ endpoint ที่ยืนยันได้ | readiness: table-model / pipeline-table-v2 not_ready; ไม่มี adapter |

REC/DET ส่ง multipart images ตามลำดับภาพ; response มี data/meta,
contract_version, kind, count, model_selection และ results
REC results มี rec_text/rec_score; DET มี dt_polys/dt_scores
ภาพสังเคราะห์1ภาพได้ DET polygon4จุด: [[24,52],[458,52],[458,78],[24,78]]
REC count1, confidence0.3303467631340027, Gateway duration497.4ms
DET count1, polygon1, duration26.43ms; ไม่มี confidence ของ recognition ที่แต่งขึ้น
ผลหนึ่งภาพไม่ได้พิสูจน์ลำดับหลายภาพหรือทุก variant ของโมเดล

LAYOUT-PIPELINE ส่ง multipart image, auto_roi_mode=text-line,
expand_text_rois=false ได้ regions1 และ data มี image/mode/regions/counts/
text_lines/auto_roi_expansion/raw/timing; duration940.08ms

ก่อนรอบตรวจนี้ Official Paddle เคยตอบ503 UPSTREAM_UNAVAILABLE และ DET smoke
เคย timeout60วินาที แต่รอบล่าสุด DET สำเร็จแล้ว ห้ามตีความ readiness เพียงอย่างเดียว
ว่า inference ของทุก model variant จะสำเร็จ

## ปิดบริการ Integrated ที่ไม่เปิดให้ใช้

ไม่ได้เรียก Official Integrated OCR หรือ Custom OCR ในรอบ audit นี้
พวก source=official ของ dynamic pipeline ยังคงเรียก Integrated Paddle แม้เลือก
execution_mode=det_rec/rec จึงไม่ถือว่าเป็น direct leaf DET/REC

ตั้ง prefix ของ paddle/custom เป็น null เพื่อบล็อกก่อนส่ง inference
สถานะและ Test Connection แสดง unavailable โดยไม่ปลอมผล OCR
สำหรับ endpoint /paddle/api/v1 ที่ไม่มี nullable map client ตรวจ readiness ก่อน
Integrated inference และไม่ POST หากบริการไม่ ready/ไม่รายงาน/ตรวจไม่ได้
บริการที่บล็อกในเครื่องมี error_code=GATEWAY_SERVICE_UNAVAILABLE และไม่มี
HTTP status ของ inference ที่แต่งขึ้น

## Railway / Local configuration

ค่าที่ผู้ใช้ระบุรองรับโดยไม่ต่อ prefix ซ้ำ:

```ini
MODEL_GATEWAY_BASE_URL=https://websolution.cdgs.co.th/paddle
MODEL_GATEWAY_API_KEY=
MODEL_GATEWAY_TIMEOUT_SECONDS=240
MODEL_GATEWAY_MAX_RESPONSE_MB=64
MODEL_GATEWAY_SERVICE_PREFIXES={"paddle":null,"custom":null,"det_rec":"/paddle/api/v1","layout":"/paddle/api/v1","status":"/paddle/api/v1"}
```

เติม key เฉพาะใน private environment ไม่เว้นวรรครอบ =
base แบบ /paddle/api/v1 ก็รองรับ; ไม่กำหนด map หรือใช้ {} สำหรับ Gateway เดิม
ต้อง reverify deployment capability ก่อนเปิด null กลับเป็น prefix
ไม่มี host, token หรือ secret ใน prefix map; API key ไม่ถูกส่งไป frontend

ชื่อ variable ใน Railway ตรวจได้แบบ read-only แต่ OAuth ไม่เปิดให้อ่านค่า
จึงไม่อ้างว่าค่า deployment จริงตรงกับข้อความที่ผู้ใช้ให้มา และไม่ได้แก้ Railway
ต้องเพิ่ม nullable prefix map ตอน release ที่ได้รับอนุมัติ ไม่มี migration ใหม่

## ความเข้ากันได้ของโค้ด

Resolver รับ path เดิม /api/v1/... ในฐานข้อมูลโดยไม่เขียนกลับ
รองรับ explicit /paddle/api/v1/... และ query version/model/weight เดิม
หาก explicit path ขัดกับ prefix ที่กำหนดให้ reject; ไม่เปลี่ยนบริการโดยเงียบ
ป้องกัน duplicate api/paddle, traversal, fragment, credentials และ host เปลี่ยน
การเลือกโมเดล, perspective crops, order, GT/CER/WER และ seed ไม่ถูกเขียนใหม่
gt_prefill_service.py จาก main ล่าสุดคงใช้ shared batch client
LAYOUT leaf และ TABLE-v2 ไม่ถูกสร้าง adapter โดยเดา contract

Gateway logs มี request_id, pipeline_id, service, endpoint_path, status,
duration และ error category ไม่มี header/body/ข้อความ OCR เต็ม
คีย์ที่เคยส่งในแชตและปรากฏใน diagnostic traceback ก่อนหน้า ควร rotate
ไม่มีคีย์อยู่ในไฟล์ที่ commit

## Git / Regression / Release

branch เดิม optimize/neon-network-transfer อยู่ที่ fbc4f03 ตาม main8 commits
ไม่มี local-only commit มี tracked edits8และ new files4 ที่ยังไม่ commit
diff สองปลายกับ main จึงแสดงไฟล์ฟีเจอร์ใหม่เหมือนหาย ไม่ใช่สิ่งที่จะนำเข้า PR

branch PR fix/cdgs-gateway-routing สร้างจาก origin/main32cc1af
apply diff CDGS แบบตรวจล่วงหน้าผ่านโดยไม่มี conflict และเก็บ worktree เดิมครบ
คง migration0011, Character Insights/Excel/GT prefill และ batch size30
ไม่ใช้ reset/stash/rebase หรือ force push

Full pytest บน main-compatible environment:425ผ่าน/53ล้มเหลว/6ข้าม
main baseline:382ผ่าน/53 failure IDs เดียวกัน/6ข้าม ไม่มี failure ใหม่
43 tests CDGS ผ่าน; tests PostgreSQL ยังข้าม ไม่มี disposable PostgreSQL ในรอบนี้
Typecheck/ESLint/build/changed-file Ruff ผ่าน ไม่มี dependency manifest เปลี่ยน
Playwright ที่เลือก:3ผ่าน/2ล้มเหลว ทั้ง PR และ main เดิมตรงกันทุก failure ID
เป็น assertion HIGHLIGHT ใน global-comparison ที่390/1440px ไม่มีการแก้หรือปิด test
npm audit แจ้ง23ช่องโหว่ของ lockfileเดิม ไม่ได้รัน audit fix หรือเปลี่ยน dependency
หลักฐาน: [validation](cdgs-gateway-validation.json)

สถานะ PR เป็น Draft: ยังขาดเอกสารและ live contract ของ LAYOUT leaf/TABLE-v2
ต้องยืนยันกับทีม CDGS ก่อนอ้างว่าครบ5บริการ ไม่มีการ merge/deploy ในรอบนี้
เมื่ออนุมัติ release ให้เปลี่ยนเฉพาะ backend URL/map/private key และตรวจ synthetic
OCR, Auto ROI และ sanitized logs อีกครั้ง ไม่เปลี่ยน frontend API URL
Rollback คืน backend deployment และ URL/map/secret revision เดิมร่วมกัน
ไม่ reset/downgrade database หรือลบ uploads

## Production release preflight (คำสั่งรอบใหม่)
ผู้ใช้ยืนยันว่า revoke/rotate key เดิมและอัปเดต Railway private secret แล้ว
ไม่ได้อ่านหรือแสดงค่า key และไม่ได้ตั้ง secret ทับผ่านเครื่องมือ
Railway source ยืนยัน repo jackchayapon/ocrtest, branch main, root /backend,
watch /backend/** โดยไม่มี volume ผูกกับ service
backend ใช้ LocalStorageService จึงยังไม่รับรองการรักษา uploads เดิมหลัง redeploy
หยุดก่อน merge/production deploy จนกว่าจะมี persistent-storage/recovery evidence
อนุญาตให้ส่ง feature branch/สร้าง Draft PR ตามคำสั่งใหม่ได้ แต่ไม่อ้างว่า
production ของ CDGS release ผ่านแล้ว ไม่มี DB migration/reset/data deletion
