# สัญญา Model Gateway และหลักฐานจาก source

ตรวจ source วันที่ 10 กันยายน 2026 ก่อนนำโฟลเดอร์อ้างอิงออก เก็บ SHA-256 ของไฟล์สำคัญใน [gateway-contract-evidence.json](gateway-contract-evidence.json) แอปไม่ import หรือเริ่มบริการจาก source นี้

## Endpoint ที่ยืนยันได้

Base URL ที่ได้รับ: `http://107.129.186.30:62051` เรียกจาก FastAPI เท่านั้น

| การใช้งาน | Endpoint/ข้อมูล |
| --- | --- |
| Mint | POST `/api/v1/ocr-results?engine=custom`, multipart `image` เป็น PNG crop |
| Hutch Crop | POST `/api/v1/ocr-results?engine=paddle`, multipart `image` เป็น PNG crop |
| Hutch Full | POST `/api/v1/ocr-results?engine=paddle`, multipart `image` เป็น PNG ภาพเต็ม ไม่มี ROI |
| Auto ROI | POST `/api/v1/document-layouts`, `image` เป็นภาพเต็มของหน้าที่เลือก, `auto_roi_mode=text-line`, `expand_text_rois=false` |
| Health | GET `/health` หรือ `/api/v1/health` ไม่ต้อง auth |
| Readiness | GET `/api/v1/readiness` ต้อง auth เมื่อปลายทางเปิดใช้ ไม่มี alias `/readiness` ที่ยืนยันจาก source |

ทั้งสอง Hutch adapters กำหนด `text_det_unclip_ratio=1.7`, `text_det_thresh=0.25`, `text_det_box_thresh=0.6` ค่า unclip เริ่มต้นใน Paddle source คือ 2.0 จึงห้ามอาศัย default ของปลายทาง

## Hutch Full ตามคำยืนยันเจ้าของ Pipeline

ไฟล์อ้างอิง `services/ocr_pipeline_paddle/main.py` เรียก `parse_image_request(request)` แล้วอ่านเพียงสาม detection fields ก่อน `model().predict(image.path, ...)` ไม่พบการอ่าน ROI หรือ crop ตาม ROI ที่เลือก `shared/api.py` เก็บ arbitrary multipart/JSON fields ได้ แต่ไม่ได้แปลว่า Paddle ใช้ field นั้น ส่วน Gateway เพียง forward image/fields ไป pipeline

Hutch Full ส่งภาพเต็มหรือหน้า PDF ที่เลือกเป็น PNG ไปยัง Paddle โดยไม่ใช้ ROI และไม่ crop ในแอป ตามคำยืนยันล่าสุดจากเจ้าของ Pipeline ไม่มีขั้นตอนรอ ROI contract

## รูปแบบตอบกลับและ tracing

สำเร็จ: `{"data": ..., "meta":{"request_id":"...","duration_ms":123.4,"service":"...","model":"..."}}`

ผิดพลาด: `{"error":{"code":"...","message":"...","request_id":"...","details":[]}}`

แอปสร้าง X-Request-ID ต่อ run ส่งต่อ Gateway และเก็บ upstream ID/เวลา/service/model แยกกัน ไม่อ้าง upstream ID ให้ข้อผิดพลาดที่เกิดก่อนเรียก Gateway ตรวจ envelope/JSON/response size และไม่ retry deterministic HTTP errors ข้อมูล sensitive ใน raw response ถูก redact ก่อน persist

## Authentication และที่มาของ key

source รองรับ Bearer ก่อน X-API-Key และ current/previous keys โดยเปรียบเทียบแบบ constant-time Gateway รับ `MODEL_GATEWAY_API_KEY`; การเรียกบริการภายในใช้ `INTERNAL_API_TOKEN` ซึ่งไม่ใช่ key ที่ต้องให้ benchmark client

`run-service.cmd` ใช้ inherited environment ไม่โหลด key เอง `model-stack.ps1`/`.sh` โหลด `MODEL_ENV_FILE` หรือ `.env.runtime`; Compose interpolate ตัวแปรจาก shell/env ของ deployment ไฟล์ runtime จริงไม่อยู่ใน source ที่ได้รับ มีเพียงค่าตัวอย่าง จึงไม่สามารถอนุมาน key ของ remote runtime ได้ ต้องขอจากเจ้าของบริการ

แอป benchmark เวอร์ชันนี้ต้องมี key สำหรับการส่ง OCR/Auto ROI; หากไม่มี คืน error ชัดเจน ไม่มีการสร้างผลแทน ทั้งนี้ source ภายนอกอาจรองรับ unauthenticated development แต่ไม่ได้ยืนยันว่าระบบปลายทางนี้เปิดใช้

## Topology และ ports ที่ตรวจพบ

Native Gateway 8080 → custom 8005 → DET V5 8002/REC Thai 8004; Paddle integrated 8006 ใช้ PP-OCRv6_medium_det + th_PP-OCRv5_mobile_rec ไม่มี model runtime ใน benchmark

Reference Compose map host 8080 → container 8000; nginx ฟัง 80/443 → 127.0.0.1:8080 ไม่พบ mapping 62051 ใน source จึงยืนยัน topology ของ public port 62051 ภายในระบบปลายทางไม่ได้

## สถานะภายนอก

ผลตรวจล่าสุด: health และ Bearer readiness HTTP 200 ใช้ key จาก private environment ทดสอบ OCR จริงด้วยภาพสังเคราะห์สำเร็จครบ Mint/Hutch Crop/Hutch Full ไม่บันทึก key ในเอกสาร

ทุก OCR Pipeline และ Auto ROI ใช้ MODEL_GATEWAY_API_KEY ตัวเดียว ไม่รองรับ secret fallback ราย Pipeline API ส่งเพียง api_key_configured boolean และไม่ส่งค่า/ส่วนของ key ออกไป
