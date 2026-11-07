# PR13: แผนรักษา uploads ก่อน cutover

สถานะ 8 พฤศจิกายน 2569: **แผนเท่านั้น — ไม่ได้ export, restore หรือแก้ production ในการรีวิวนี้**
หลักฐานเดิม 50/50 Dataset samples มี source ไม่ใช่ inventory ของ originals ทั้งหมด และไม่ใช่ backup
ฐานข้อมูลเก็บ references/GT ไม่สามารถสร้างภาพ/PDF ต้นฉบับที่สูญหายกลับมาได้

## ผู้รับผิดชอบและเงื่อนไขก่อนเริ่ม

ต้องอนุมัติการคัดลอกข้อมูลส่วนบุคคล, ปลายทาง, ผู้มีสิทธิ์ถอดรหัส, retention และช่วงหยุดเขียนก่อน
ระบุ production deployment ID, environment, STORAGE_PATH ที่ resolve แล้ว และเจ้าของ filesystem จริง
ห้าม mount ทับ path ปัจจุบันหรือ replace container ก่อน backup ผ่าน
SSH key ควรจำกัด environment/service/คำสั่งอ่านและอายุ; ถ้า platform จำกัดได้เพียงระดับบัญชี ให้บันทึกว่ามิใช่ least-privilege shell จริงและใช้ผู้ดูแลควบคุมคำสั่ง

## ขั้นตอนเมื่อได้รับอนุญาตแยกต่างหาก

1. ใช้ read-only transaction เก็บ document ID → storage_key, ประเภท, checksum/ขนาดที่มี โดยไม่อ่าน OCR/GT ที่ไม่จำเป็น สำรวจ schema ก่อน query และรวม references ที่ใช้ไฟล์เดียวกัน
2. สำรวจ regular files ภายใน root จริง ไม่ follow symlinks ออกนอก root แยก originals/PDF ออกจาก generated previews/temp; ห้ามแทน PDF ต้นฉบับด้วย PNG ของหน้า
3. Reconcile แบบหนึ่ง key ต่อไฟล์: referenced-present, referenced-missing, unreferenced, unsafe-path, unreadable และ changed-during-scan เก็บ count, bytes, SHA-256 และ stat ก่อน/หลังอ่าน ไม่มี filenames/IDs/hashes รายไฟล์ใน public logs
4. ถ้าไฟล์เปลี่ยนขณะอ่าน ให้ retry ภายใต้ช่วง consistency ที่ตกลง ไม่ถือว่าผ่านเพียงเพราะ counts เท่ากัน
5. สร้าง temporary SSH key แบบมี passphrase/ACL; pin/verify server identity ผ่าน provider ไม่ปิด host verification ไม่ส่ง private key ผ่าน Git/chat/logs
6. Stream ผ่าน authenticated SSH/SFTP จาก instance ที่ระบุ เข้ารหัสก่อนลง disk local; ไม่สร้าง plaintext archive บนเครื่อง shared หรือ project workspace ใช้ chunks จำกัด RAM ไม่อ่าน uploads ทั้งหมดเข้าหน่วยความจำ backend 512MB
7. Manifest ต้องอยู่ใน encrypted package ด้วย ระบุ format version, chunk order/length, per-file SHA-256 และ aggregate digest ของ canonical manifest; authenticated encryption ต้องตรวจ truncation/reordering ได้ DPAPI ต่อ chunk อย่างเดียวไม่เพียงพอถ้าไม่มี authenticated index
8. DPAPI CurrentUser ผูกกับ Windows account/เครื่องโดยทั่วไป ห้ามใช้ LocalMachine เพื่อให้ user อื่นถอดได้ ไม่ถือว่าไฟล์ .dpapi เพียงไฟล์เดียวเป็น disaster recovery ต้องกำหนด recovery identity/key escrow ที่องค์กรอนุมัติและทดสอบบนเครื่องสำรอง หากใช้ EFS ต้อง backup certificate/private key อย่างปลอดภัยแยกจากข้อมูล
9. Restore drill ใน encrypted local volume ที่มี ACL เฉพาะผู้ดูแลและ test destination ใหม่ ห้าม extract absolute paths, `..`, symlinks/hardlinks หรือ overwrite path นอก root ห้ามเปิด network serving ของ restored private files
10. ตรวจทุกไฟล์: count, size, SHA-256, aggregate manifest และ DB-reference mapping; ตรวจโครงสร้าง PNG/PDF เท่าที่จำเป็นโดยไม่แสดงเนื้อหาใน logs เก็บผล aggregate PASS/FAIL เท่านั้น
11. ก่อน final cutover ต้อง freeze **ทุกช่องทางเขียน** (upload/delete/bulk cleanup/worker/jobs/admin/API clients) ไม่ใช่แค่ปิดปุ่มหน้าเว็บ รอ active jobs/checkpoints แล้ว snapshot references และทำ final incremental inventory/backup อีกครั้ง ห้ามอ้าง repeatable-read DB transaction ทำให้ filesystem consistent เอง
12. หลัง backup/restore drill ผ่านและอนุมัติ deployment จึงสร้าง durable destination ตามแผนที่อนุมัติ ทดสอบ permission/ownership ด้วย runtime UID จริง (Dockerfile ใช้ UID 10001) ห้าม chmod 777 ใช้ staging path ก่อน atomic promotion ภายใน filesystem เดียวกัน
13. Restore **original keys และ bytes** โดยไม่แก้ DB ชี้ไปไฟล์อื่น ตรวจ mapping และ hash ครบทุก referenced-present เดิมก่อนเปิด traffic ใช้ synthetic canary ไม่เปิดเอกสารจริงผ่าน public test logs
14. ถ้า missing/hash mismatch: คง write freeze, หยุด cutover, รักษา instance เก่าถ้ายังอยู่ ห้าม delete/truncate references คืน code version และไฟล์จากชุดที่ตรวจแล้ว อย่าอ้าง code rollback คืน ephemeral uploads ได้ หาก original สูญหายจริง ให้ระบุรายการใน encrypted manifest และขอ restore/re-upload
15. เมื่อ verify ครบ ถอน temporary SSH key, ตรวจว่าใช้ไม่ได้แล้ว, ล้าง temporary plaintext/credentials ตาม retention ที่อนุมัติ รักษาสำเนา encrypted และ audit hashes จนพ้น recovery window ไม่อ้าง secure erase บน SSD โดยไม่มีหลักฐาน

## ทางเลือกความคงทนและค่าใช้จ่าย

- Restore เข้า ephemeral container เป็นเพียง recovery ชั่วคราว: redeploy ครั้งถัดไปยังเสี่ยงสูญหาย **ไม่ผ่าน durability gate**
- Railway persistent volume ใช้ LocalStorageService เดิมได้หลังตรวจ mount/ownership แต่ต้องมี backup แยกและทดสอบ restore; ราคาอ้างอิง storage $0.15/GB/เดือน เช่น 10GB ประมาณ $1.50/เดือน เฉพาะ storage ไม่รวม compute/network/backup/แพ็กเกจ ตรวจยอดจริงและอนุมัติก่อนสร้าง ตาม [Railway pricing](https://docs.railway.com/pricing/plans) และ [volume reference](https://docs.railway.com/volumes/reference)
- Object storage แบบ private พร้อม versioning/lifecycle แยก durability จาก compute ได้ แต่ต้องทำ adapter/access-control/การทดสอบเพิ่มเติม ประเมินค่า GB-month + requests + egress + retained versions ตาม provider ที่เลือก; ยังไม่มี provider/quotation จึงไม่ระบุราคาปลอม
- ข้อจำกัด DPAPI อ้างอิง [Microsoft CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata) ไม่ใช้ DPAPI แทนแผนกู้คืน account/เครื่อง

**Go gate:** inventory ครบ, missing เก่าระบุชัด, originals ที่มีอยู่สำรองและ restore drill ผ่าน, recovery key ใช้งานได้, final freeze/delta ผ่าน, durable target และ rollback ได้รับอนุมัติ ไม่มีขั้นใดถูก execute ในงาน audit นี้
