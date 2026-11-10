# PR #13: แผนสิทธิ์เข้าถึงและการรักษา uploads

ขอบเขต remediation นี้เป็น local isolated tests เท่านั้น ไม่มีการอ่านเอกสาร Production, เปลี่ยน secrets, mount volume, restart หรือ deploy

## การป้องกันที่ทำได้ใน PR นี้

ปิด `SafeDebugPanel` แบบ fail closed: ไม่มี toggle, diagnostics payload, IDs, raw response หรือ localStorage switch ที่เปิดกลับได้ หน้าเว็บแสดงเพียงข้อความว่าต้องมีระบบตรวจสิทธิ์ก่อน การซ่อนนี้ลดข้อมูลเพิ่มเติมที่หน้าจอ แต่ **ไม่ใช่ authorization** และไม่ปิดช่องโหว่ของ API เดิม

Documents, Jobs, History, Dataset และ endpoints ที่เข้าถึงเนื้อหา OCR/GT ยังไม่มีการผูกเจ้าของและตรวจสิทธิ์ผู้ใช้ การใช้ UUID, CORS, UI ที่ซ่อนปุ่ม หรือ API key ของ Gateway ไม่ใช่การป้องกันการเข้าถึงข้อมูลผู้ใช้

## แผน implementation แยกจาก PR นี้

1. ยืนยันขอบเขตองค์กร/tenant, ผู้ดูแล, ผู้ตรวจ GT และผู้ดูอย่างเดียว เลือก identity provider และวิธีส่ง session/access token ระหว่าง frontend กับ backend ตรวจ signature, issuer, audience, expiry ที่ backend ไม่รับ user/tenant จากค่าที่ client อ้างเอง
2. ออกแบบ migration ใหม่แยก PR: ownership/tenant ของ document, test case และ job; foreign keys/indexes และ audit retention ให้ครบ ไม่แก้ migration เก่า ข้อมูลเดิมที่ยังระบุเจ้าของไม่ได้ต้องเป็น admin-only/quarantined ก่อนให้ผู้ใช้ทั่วไปเห็น ห้าม assign ให้ผู้ใช้คนแรกโดยอัตโนมัติ
3. ใช้ query scope เดียวสำหรับ document metadata/image/crop/PDF, case/results/GT/fields, job create/status/results/cancel, History, Matrix/Error Analytics, Dataset eligibility/ZIP/Excel/evaluation export, bulk delete/exclusion และ pipeline/model settings ตรวจสิทธิ์ **ทุก ID ใน bulk request** รวม download และ worker recovery ห้ามเพียงตรวจหน้า list
4. Worker ใช้ service identity แยกจากผู้ใช้ รักษา tenant/job ownership ใน checkpoint และ idempotency key; ผู้ใช้ที่ไม่มีสิทธิ์ต้องไม่ค้นพบสถานะ job หรือผลของผู้อื่นผ่าน ID เดาได้
5. Debug ปิดไว้จน middleware และ backend RBAC ผ่านจริง หลังเปิดให้เฉพาะ admin/support role ที่อนุมัติ ใช้ response allowlist ไม่ให้ headers/credentials/raw images/OCR เต็ม/paths ส่วนตัวหลุดออกมา มี audit ที่ไม่เก็บเนื้อหาเอกสาร
6. เก็บ original ใน private storage; download ผ่าน authorized backend หรือ URL อายุสั้นหลังตรวจสิทธิ์ ไม่เปลี่ยน bucket เป็น public และไม่ใส่ credentials ใน URL/browser bundle
7. Rollout: staging ข้อมูลสังเคราะห์ → ทดสอบ cross-user/cross-tenant ทุก read/write/export/job → backfill ownership ที่ยืนยันแล้ว → สำรอง/restore drill → deploy middleware+schema compatible → เปิด authenticated traffic เท่านั้น ไม่มี fallback อนุญาต anonymous เมื่อ token ผิด/ขาด
8. Rollback ต้องรักษา ownership/schema และปิด traffic ที่ต้องมีสิทธิ์หาก code เก่าไม่รองรับ ห้าม rollback เป็น anonymous access เพื่อรักษา uptime

Acceptance ต้องมี unauthorized=401, forbidden=403/404 ตามนโยบาย, job/export ที่ถูกเพิกถอนสิทธิ์ไม่ส่งข้อมูล, cache แยกผู้ใช้และ `no-store` สำหรับข้อมูลส่วนตัว รวม CSRF/session logout/expiry และ log-redaction regression

## Upload preservation: ยังไม่ execute

ใช้ [runbook](pr13-upload-recovery-runbook.md) เป็นขั้นตอนจริง: inventory DB references กับ runtime files → encrypted backup/manifest → restore ในระบบแยก → freeze ทุกทางเขียน/worker และ final delta → ตรวจ durable target/UID/permissions → cutover เฉพาะเมื่ออนุมัติ → ตรวจ hash/mapping ก่อนเปิด traffic

- Local persistent volume ใช้ StorageService เดิมได้และเปลี่ยนโค้ดน้อย แต่ต้องยืนยัน mount path/ownership, backup ที่แยกจาก volume, retention และ restore drill ก่อน deploy ห้าม mount ทับต้นทางก่อนสำรอง
- Private object storage แยกไฟล์จาก container และรองรับ versioning ได้ แต่ต้องมี adapter, IAM, authorized download, migration/rollback และการทดสอบเพิ่ม จึงไม่แอบเปลี่ยนใน PR นี้
- ค่าใช้จ่ายต้องรวม GB-month, retained backup versions, requests, egress, compute และผู้ดูแล ผู้ให้บริการ/ขนาดจริงยังไม่ยืนยัน จึงไม่มีใบเสนอราคาหรือการสร้าง resource ในงานนี้
- DPAPI ผูกกับ Windows identity/เครื่อง การมีไฟล์ encrypted อย่างเดียวไม่พิสูจน์ disaster recovery ต้องมี recovery identity/key escrow และทดสอบบนเครื่องสำรองตามนโยบาย
- DB records ไม่สามารถสร้าง original ที่สูญหายกลับมาได้ ต้องคืนจากสำเนาที่ตรวจแล้วหรือ re-upload ไม่มีการสร้างภาพ/labels ทดแทน

ต้องอนุมัติแยกก่อนอ่าน/คัดลอก private uploads, สร้าง storage/ค่าใช้จ่าย, mount, เปลี่ยน environment, freeze traffic หรือ deploy ทั้งหมดนี้ยังเป็น release gates ที่ไม่ผ่านจาก local tests
