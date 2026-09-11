# ผลตรวจสอบ OCR Testing & Benchmark

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
