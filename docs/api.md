# คู่มือ API สำหรับเชื่อมต่อแอป Benchmark

เรียก FastAPI ของแอป เช่น `http://localhost:8000` ไม่เรียก Gateway จาก frontend และไม่ส่ง Gateway key ให้ browser OpenAPI อยู่ที่ `/docs` และ `/openapi.json`; response dictionaries บางส่วนอธิบายเพิ่มเติมด้านล่าง

ID เอกสาร/case เป็น UUID ส่วน Pipeline ID มีเพียง `mint`, `hutch_crop`, `hutch_full` การสร้างเอกสาร/case คืน 201 การทำงานปกติอื่นคืน 200 JSON request ไม่รับ field ที่ไม่รู้จัก Sensitive responses ใช้ no-store ไม่มีระบบ login ใน MVP ให้ใช้ภายใต้ขอบเขตการเข้าถึงที่เชื่อถือได้

## รายการเส้นทาง

| Method | Path | การใช้งาน |
| --- | --- | --- |
| GET | `/api/health` | สถานะ app/database/storage; 503 ถ้าไม่พร้อม |
| GET | `/api/upload-config` | upload limit และ PDF DPI เท่านั้น |
| POST | `/api/documents` | multipart field **file**; เก็บเอกสาร |
| GET | `/api/documents/{id}` | metadata; query `page_number` สำหรับ PDF |
| GET | `/api/documents/{id}/image` | ภาพ PNG; PDF ใช้หน้าแรก |
| GET | `/api/documents/{id}/pages/{page_number}/image` | PNG ของหน้า PDF ที่เลือก |
| GET | `/api/documents/{id}/crop` | PNG preview; query x1,y1,x2,y2 และ page_number |
| POST | `/api/documents/{id}/auto-rois` | เสนอ ROI ไม่รัน OCR |
| POST / GET | `/api/test-cases` | สร้าง / รายการ case |
| GET / PUT | `/api/test-cases/{id}` | อ่าน / แก้ field ที่รองรับ |
| PUT | `/api/test-cases/{id}/roi` | แก้ ROI ก่อนมี run |
| PUT | `/api/test-cases/{id}/ground-truth` | แก้ GT และคำนวณ metrics ใหม่ |
| PUT | `/api/test-cases/{id}/categories` | category_codes หลายค่า |
| POST | `/api/test-cases/{id}/run` | รัน pipelines ที่เลือกและ persist ผล |
| GET | `/api/test-cases/{id}/results` | ผลที่ไม่ archived |
| GET | `/api/history` | ประวัติพร้อมเอกสาร/GT/categories/runs |
| GET | `/api/categories` | manual categories |
| GET | `/api/matrix` | ค่าเฉลี่ยต่อ Pipeline |
| GET | `/api/analytics/categories` | ผลต่อ category/Pipeline |
| GET | `/api/pipelines` | non-secret configurations |
| GET / PUT | `/api/pipelines/{pipeline_id}` | อ่าน/แก้ configuration |
| POST | `/api/pipelines/{pipeline_id}/test-connection` | readiness หรือสถานะ contract/key ไม่ใช่ inference |
| GET | `/api/integrations/model-gateway/status` | gateway/pipeline availability และ key presence |

## Request ที่ใช้บ่อย

หลัง upload ให้ใช้ document ID จริงในการสร้าง case ตัวอย่าง JSON นี้เป็น **API ภายในแอป** ไม่ใช่ ROI wire format ของ Hutch:

```json
{
  "document_id": "00000000-0000-4000-8000-000000000001",
  "page_number": 2,
  "roi": {"x1": 10, "y1": 20, "x2": 200, "y2": 100},
  "ground_truth_raw": "บริษัท ซีดีจี จำกัด",
  "category_codes": ["thai_text", "stamp"]
}
```

ภาพธรรมดาไม่ส่ง page_number; PDF นับหน้าจาก 1, default 1 ROI เป็น integer pixel ของภาพต้นฉบับ/selected raster ขอบขวาล่าง exclusive, null ใช้ภาพเต็ม หลังมี run เปลี่ยน ROI จะได้ 409 ให้สร้าง case ใหม่ GT แก้ได้โดยไม่เปลี่ยน OCR prediction

รัน: `{"pipelines":["mint","hutch_crop","hutch_full"]}` รับ 1–3 IDs ไม่ซ้ำ คืน `{"test_case_id":"...","runs":[...]}` แม้บาง pipeline error ก็ยังคืน HTTP 200 และผลอื่นไม่ถูกยกเลิก ต้องตรวจ status ทุกรายการ การเรียกซ้ำเพิ่ม run ใหม่

แก้ GT: `{"ground_truth_raw":"ข้อความที่ถูกต้อง","confirmed":true}`; category: `{"category_codes":["thai_text"]}`; Auto ROI: `{"page_number":2,"auto_roi_mode":"text-line","expand_text_rois":false}` mode ของ Auto ROI เลือก text-line/layout/hybrid ซึ่งเป็นรูปแบบ detection ไม่ใช่ตัวเลือกสร้างผล OCR

Filter: category, pipeline, date_from/date_to (วันที่สร้าง case ตาม UTC, รวมวันสุดท้าย), document; รายการและ History เพิ่ม limit 1–200 (default 50), offset (default 0) ไม่มี execution-mode filter

Pipeline settings รับ name, base_url, endpoint, enabled, POST, request_format multipart/json_base64, file_field_name=image, engine/query_params engine ที่ตรงกับ pipeline และ include_roi=false ซึ่งเป็น field compatibility เก่าและไม่ใช่การกำหนด ROI wire format ห้ามใส่ key/credentials/query secrets ใน URL การเปลี่ยน settings กระทบผู้ใช้ API ร่วมกัน

## Response หลัก

Document มี id/filename/mime_type/storage_key/sha256/width/height/document_type/page_count/pdf_render_dpi/page_number/image_url/created_at; image_url เป็น path เทียบ backend

TestCase มี document_id, document, page_number, roi, ground_truth_raw/normalized, status draft/tested/confirmed, categories, runs, created_at/updated_at

| Run fields | ความหมาย |
| --- | --- |
| pipeline_id/name, id, status, created_at | ตัวตนและผลสำเร็จ/error |
| raw_text, final_text, normalized_text, text | prediction; text alias ของ final |
| metrics, raw_metrics | null หรือ cer/wer/exact_match แยก final/raw |
| confidence, boxes | ค่าจริงที่ upstream มี ไม่มีค่าจะเป็น null/ไม่มี geometry |
| original_width/height, roi | ขนาดภาพต้นฉบับ/selected page และ ROI |
| input_width/height/sha256, input_byte_size/format | ภาพที่ adapter เตรียม; ไม่รับประกันว่าส่งสำเร็จ |
| crop_width/height/sha256, crop_stage | Mint/Crop ใช้ app_crop; Full crop fields null และ full_image |
| processing_time_ms, gateway_duration_ms | เวลาภายใน adapter และเวลาที่ Gateway รายงานแยกกัน |
| request_id, gateway_request_id | ID ของเราและ upstream ไม่สร้าง upstream ID ให้ local error |
| detector_model, recognizer_model, gateway_service/model, model_info | tracing ของโมเดลและบริการ |
| raw_response | envelope หลัง redact ข้อมูลลับและภาพฝัง ไม่ใช่ unrestricted dump |
| error_code/message | ข้อผิดพลาดปลอดภัย เช่น MISSING_GATEWAY_KEY หรือ GATEWAY_UNAVAILABLE |

Box มี bbox/polygon ในพิกัดเอกสาร, crop_bbox/crop_polygon ในพิกัด crop, text, det_confidence/rec_confidence/confidence สำหรับ Mint/Crop offset ด้วย ROI origin ส่วน geometry contract ของ Hutch Full ต้องยืนยันจากบริการก่อนใช้งานจริง

Matrix มี tests/successful_runs/failed_runs/evaluated_runs, cer/wer/exact_match_rate, avg_time_ms/avg_gateway_time_ms/avg_confidence ค่าความแม่นยำเป็น ratio ไม่ใช่เปอร์เซ็นต์ เลือก latest run ต่อ case/pipeline ตัด archived และ Full semantics เก่าออก Category analytics คืน code/display_name/test_cases/pipelines

## ตัวอย่าง PowerShell

```powershell
curl.exe -f -X POST http://localhost:8000/api/documents -F 'file=@frontend/public/sample-document.png;type=image/png'
# สร้าง case.json ด้วย ID จริงจาก upload แล้วส่งไฟล์เพื่อหลีกเลี่ยงปัญหา quoting
curl.exe -f -X POST http://localhost:8000/api/test-cases -H 'Content-Type: application/json' --data-binary '@case.json'
# run.json: {"pipelines":["mint","hutch_crop","hutch_full"]}
curl.exe -f -X POST http://localhost:8000/api/test-cases/YOUR_CASE_ID/run -H 'Content-Type: application/json' --data-binary '@run.json'
```

เมื่อไม่มี key ผล run เป็น error ชัดเจน แต่ยังใช้อัปโหลด เตรียม ROI/GT และประวัติได้ รายละเอียด external contract อยู่ใน [model-gateway.md](model-gateway.md)
