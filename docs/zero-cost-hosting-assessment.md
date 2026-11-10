# OCRLab — ตรวจ hosting งบ 0 บาท

## Final scoped G10 assessment — release10พฤศจิกายน

**PASS สำหรับการปล่อยเดโมส่วนบุคคลเพื่อการศึกษาแบบจำกัดการใช้งานบนบริการเดิม โดยไม่เปิด paid operation/resource ใหม่** ไม่ใช่การรับประกัน unlimitedquota/24×7 หรือ account-levelbillingที่เครื่องมือไม่มีสิทธิ์ตรวจ

- Vercel teamเดิมเป็นHobby/active/nontrial ผู้ใช้ยืนยันไม่มีค่าจ้างพัฒนา/ดูแลและเป็นเดโมส่วนบุคคลเพื่อการศึกษา สอดคล้องกับpublishedpersonal/noncommercialuse ไม่ประเมินจากบริษัทในอนาคต ไม่มีproject/planใหม่
- RailwayยังFREE512MB/1CPU/1replica/sleep=true;เครดิตล่าสุด$0.7460524307,freeplanไม่exhausted ไม่เพิ่มRAM/CPU/replica/volumeหรือsubscription ใช้existingauto-deployสองระบบและboundedliveinferenceเท่านั้น จำกัด demonstration sessions และยอมรับsleep/หยุดบริการเมื่อquotaหมด
- Neonเดิมอ่านเฉพาะaggregate/schemaแบบreadonly:53,354,496bytes,1connection,revision0012 ไม่มีการเพิ่มplan/project/computeหรือmigration และเพิ่มเฉพาะsyntheticrecordsสำหรับE2E Accountbilling/remainingCU-hoursยังไม่exposed ไม่เรียกว่าquotaverifiedหรือรับรองอนาคต แต่ไม่ใช่หลักฐานว่าการใช้บริการเดิมแบบจำกัดนี้ต้องซื้อhostingเพิ่ม
- CDGSใช้integration/entitlementเดิมที่ทีมให้ใช้;DET6/REC5จริงตอบ200กับภาพสังเคราะห์ และRailwaykeyhealth/readinessconnected DET/RECavailable ไม่มีการซื้อintegration/modelหรือเปิดpaidserviceใหม่ Accountrequestbudgetไม่exposed จึงจำกัดcallsและรายงาน429/availabilityตามจริง ไม่มีunlimitedinferenceclaim

ขอบเขตนี้ปิดblockerจากความไม่แน่นอนที่ไม่เกี่ยวกับการจัดซื้อใหม่ตามคำสั่งล่าสุด ข้อจำกัดquotaยังเป็นoperationalriskที่ต้องติดตาม ไม่เปลี่ยนunknownaccountbillingเป็นตัวเลขศูนย์ และไม่อัปเกรดอัตโนมัติหากquotaหมด

## Earlier assessments — retained history, superseded scope/decision

## ผลล่าสุด — 10 พฤศจิกายน 2569

ขอบเขตปัจจุบันคือ **internship prototype / development / demonstration** ไม่ใช่ระบบองค์กรถาวร ไม่ใช้การนำไปใช้ในบริษัทในอนาคตเป็นเหตุ BLOCK และไม่ถือว่าคำว่า internship ทำให้ผ่านเงื่อนไข personal/non-commercial โดยอัตโนมัติ งบเพิ่มยังเป็น 0 บาท ไม่มีการเปลี่ยน plan, RAM, CPU, replica, volume, URL หรือผู้ให้บริการ

| ระบบ | ตรวจใหม่และสิ่งที่ยังยืนยันไม่ได้ |
|---|---|
| Railway | Read-only API/CLI ยืนยัน FREE, RAM512,000,000bytes, 1CPU, 1replica; `remainingUsageCreditBalance=0.7492306288080863`, `hasExhaustedFreePlan=false`. รอบ 14 ต.ค.–14 พ.ย. ใช้ $0.2507693712 และคาดการณ์ $0.3369235438. เป็น metered usage ไม่ใช่หลักฐานว่าชำระเงินจำนวนนี้ และไม่รับประกันว่าทราฟฟิกหลัง release จะเท่าเดิม |
| Vercel | GET team เดิมยืนยัน Hobby/active/non-trial. ผู้ใช้ยืนยันว่า **ไม่มีค่าจ้างสำหรับพัฒนา/ดูแล เป็นเดโมส่วนบุคคลเพื่อการศึกษา** ซึ่งสอดคล้องกับ personal/non-commercial ใน [Hobby](https://vercel.com/docs/plans/hobby) และ [Fair Use](https://vercel.com/docs/limits/fair-use-guidelines#commercial-usage). ไม่ใช้การนำไปใช้ในบริษัทในอนาคตเป็น blocker และไม่อ้างว่าได้รับ exemption เป็นพิเศษจาก Vercel; หากเปลี่ยนเป็นการใช้งานเชิงพาณิชย์ต้องทบทวนใหม่ |
| Neon | Revision/schema compatibility จาก metadata-only audit เดิมและ local migrations ใช้ได้ ไม่มี schema change ใหม่ แต่ยังไม่ยืนยัน account plan, usage และ remaining quotas ผ่าน billing console; SQL credential ไม่ได้ให้สิทธิ์ยืนยัน billing |
| CDGS | ไม่มีการเพิ่ม paid integration. Contract/routing ผ่าน mocked regressions; entitlement/usage budget และ live inference รอบ release นี้ยังไม่ได้ยืนยัน ไม่ใช้ API key เป็นหลักฐานว่าไม่มีค่าใช้จ่ายหรือโควตาไม่จำกัด |

สำหรับเดโมจำกัดเวลา ตัวอย่างประมาณ **6 ชั่วโมง active/เดือน, RAMเฉลี่ย0.25GB, CPUสูงสุด1coreระหว่างactive, egress1GB/เดือน** คิดจาก [ราคา Railway](https://docs.railway.com/pricing/plans) ได้ประมาณ $0.238 ของ usage/เดือน ก่อน sleep/cold-start/บริการอื่นและการใช้งานจริง นี่เป็น scenario เพื่อวาง budget ไม่ใช่ measured demand หรือโควตาที่ reserve ไว้ ยอดปัจจุบันต่ำกว่าเครดิต แต่ public anonymous traffic อาจใช้เครดิตหมด ต้องยอมรับการพักบริการและติดตาม quota ไม่รับรอง 24/7 หรือ unlimited use

**Vercel personal-use assessment ผ่านตามข้อเท็จจริงที่ผู้ใช้ยืนยัน; G10 รวมยัง BLOCKED** เพราะ account quotas ของ Neon/CDGS ยังไม่ครบ ไม่ใช่เพราะต้องซื้อ enterprise hosting ไม่มีการย้าย platform หรือขอค่าใช้จ่ายที่ผู้ใช้ปฏิเสธอีก

## ประวัติการประเมิน 9 พฤศจิกายน — ขอบเขต/limits เก่าด้านล่างไม่ใช่ข้อสรุปปัจจุบัน

ตรวจ 9 พฤศจิกายน 2569 · **G10 BLOCKED** · ไม่ซื้อแพ็กเกจ ไม่สร้างบริการ cloud ใหม่ ไม่ย้าย platform

งบที่ยืนยันล่าสุดคือ recurring infrastructure **0 THB/เดือน** การอนุมัติ RAM ก่อนหน้านี้ไม่ใช่สิทธิ์เปลี่ยน Railway เป็น Hobby และผู้ใช้ปฏิเสธ paid plan/RAM โดยชัดเจนแล้ว ไม่มีการขออนุมัติค่าบริการซ้ำเพื่อบังคับปล่อยงาน

## ระบบที่ใช้อยู่

| ระบบ | ข้อเท็จจริงที่ยืนยัน / ข้อจำกัด |
|---|---|
| Railway | API ยืนยัน `FREE`, RAM512,000,000bytes/1CPU/1replica; [Free plan](https://docs.railway.com/pricing/plans) มีเครดิต $1/เดือน ไม่ใช่ compute ไม่จำกัด ไม่เปลี่ยน plan/limit/sleep mode/volumes ผล final512MB ยังไม่มี memory margin สำหรับ40MP จึงไม่เป็น target ที่ปล่อยได้อย่างปลอดภัย |
| Vercel | Read-only GET team ผ่าน CLI ที่ตรวจ syntax แล้ว: `hobby`, `active`, ไม่ใช่ trial. [Hobby](https://vercel.com/docs/plans/hobby) จำกัด personal/non-commercial use; [Fair Use](https://vercel.com/docs/limits/fair-use-guidelines#commercial-usage) รวมกรณีพนักงาน/consultantได้รับค่าจ้างพัฒนา จึงยังรับรอง eligibility สำหรับงานองค์กรนี้ไม่ได้ ไม่ตีความว่าไม่มีหน้ารับชำระเงินแล้วใช้ Hobby ได้เสมอ ต้องยืนยันสิทธิ์กับผู้ให้บริการหรือเลือก target ที่เข้าเงื่อนไข |
| Neon | ไม่เปลี่ยน DB/plan. [ประกาศ Free ปัจจุบัน](https://neon.com/blog/neon-free-plan-1-gb-per-project) ระบุ100CU-hours/เดือนและ1GBstorageต่อproject พร้อม6-hourrestore window; [รายละเอียด Free](https://neon.com/blog/how-to-make-the-most-of-neons-free-plan) อธิบาย outbound quota5GB/เดือน. ไม่ใช้ตัวเลข0.5GBจากเอกสารเก่ามารับรองปัจจุบัน แต่ **ยังไม่ได้ยืนยัน account plan/usage/remaining quotas ของ Production จริง** เพราะ DATABASE_URL ให้เข้าถึง SQL ไม่ใช่ billing console |

Vercel billing-charges endpoint ตอบ404 `costs_not_found` ไม่ใช่หลักฐานว่า invoice/usage ทั้งหมดเป็นศูนย์ ค่าใช้จ่ายจริงและ remaining quotas ต้องตรวจที่บัญชีที่มีสิทธิ์ ไม่มีการดึงข้อมูลบัตร/credentialsมาใส่ report

Railway compute/storageใช้เครดิตร่วมกัน; [FAQ](https://docs.railway.com/pricing/faqs) ระบุว่างานอาจหยุดเมื่อถึง usage limits การไม่คิดเงินเพิ่มอัตโนมัติไม่ใช่หลักฐาน availability ต่อเนื่อง และการสมัคร trial/เปลี่ยนบัญชีวนไม่ใช่แผน sustainable free hosting

## ทางเลือกที่ตรวจจากเอกสารทางการ

| ทางเลือก | ความเข้ากันได้ / เหตุที่ยังไม่เลือกปล่อย |
|---|---|
| Render Free | [Compute plans](https://render.com/docs/compute-plans) ระบุ512MB/0.1CPU จึงไม่ได้เพิ่ม RAM จาก RailwayFREE; [free instances](https://render.com/docs/free) มีsleep,750instance-hours/เดือน,ephemeral filesและquota/egressเงื่อนไขเพิ่มเติม ไม่มีหลักฐานว่าค่าใช้จ่าย/availability/workerนี้ผ่าน;ไม่ย้ายNeonไปFreeRenderPostgresที่หมดอายุ30วัน |
| Hugging Face Spaces | [Spaces docs](https://huggingface.co/docs/hub/spaces-overview) แยก CPU Basic hourlyFREE16GB ออกจาก **account plan**: การสร้างDocker/Gradio compute Spaceปัจจุบันต้องpaidplan และ outboundอนุญาต80/443/8080เท่านั้น PostgreSQL/psycopgไปNeon5432ไม่ใช่drop-in;จึงไม่อ้างว่า16GBแปลว่าทั้งระบบใช้ฟรี |
| Oracle Always Free | [Always Free compute](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) มีAMDmicro1GB/1⁄8OCPU และA1รวม2OCPU/12GBตามเอกสารปัจจุบัน ไม่ใช้ตัวเลข24GBเก่า;มีhome-region/capacityและidle-reclamationเงื่อนไข [FAQ](https://www.oracle.com/cloud/free/faq/) กำหนดidentity/card verificationและห้ามหลายfreeaccounts. เป็นผู้สมัครที่ควรประเมิน แต่ **ไม่มี tenancy/available AlwaysFree quota/approved migration ที่ยืนยันผ่านเครื่องมือนี้** และยังไม่วัดruntime/ARM wheels/TLS/domain/Neon/GatewayบนVMจริง จึงไม่แอบสมัครหรือย้ายProduction |
| Cloud Run | [Pricing](https://cloud.google.com/run/pricing) ระบุ free quota แล้วคิดเงินเมื่อเกิน;[instance billing](https://docs.cloud.google.com/run/docs/configuring/billing-settings) มีผลต่อCPUของbackgroundwork ไม่ใช่ย้ายHTTP202workerแล้วใช้ฟรีแน่นอน ไม่มีhardzero-billconfiguration/accountที่ยืนยัน จึงไม่provision |
| Cloudflare | [Workers Free](https://developers.cloudflare.com/workers/platform/limits/) มี128MB/10msCPUต่อrequest ไม่ใช่drop-inของPython/Pillow/OpenCV/DurableWorker. [Pages static Next.js](https://developers.cloudflare.com/pages/framework-guides/nextjs/deploy-a-static-nextjs-site/) ต้องstaticexport;frontendปัจจุบันมีdynamicroutes จึงยังไม่ยืนยันcompatibilityและไม่เปลี่ยนarchitecture/URLเพื่อเลี่ยงVercelterms |

ไม่สรุปว่าโลกนี้ไม่มีทางเลือกฟรี สรุปเฉพาะว่า **ยังไม่มี target ที่ตรวจครบทั้ง capacity, sustainablequota,องค์กรใช้ได้,ไม่เกิด billableoverage,domain/HTTPS,backgroundworker,Neon/Gatewaycompatibilityและdata-safe rollout** จึงให้G10PASSไม่ได้

## สิ่งที่ยังไม่ทำ และเงื่อนไขกลับมาปล่อย

- ไม่เพิ่ม RAM/CPU/replica/volume ไม่เปิด paid plan/trial และไม่สร้างบัญชีหรือย้าย hosting
- ไม่ downgrade/reset/delete Neon เพื่อทำให้ค่าใช้จ่ายเป็นศูนย์ และไม่อ่าน/ย้าย Production uploads
- ไม่ลด40MP/upload/concurrency limits เงียบ ๆ เอกสาร0.8MPผ่านlocalmemoryไม่เท่ากับ40MPผ่าน และไม่ใช่การอนุมัติลดproductcapability
- ทางต่อที่ไม่เสียเงินต้องเป็น target/บัญชี/quotas/eligibility ที่ตรวจยืนยันได้ พร้อมทดสอบcandidateจริงและอนุมัติmigrationที่จำเป็น หรืออนุมัติmaterial workload/admission changeที่วัดแล้วโดยชัดเจน ไม่ขอให้ซื้อแพ็กเกจเป็นคำตอบของงานนี้
- หลังปลดG6/G10จึงทวนrollout/rollbackและG1–G11 แล้วค่อยnormalPRmerge→auto-deploy→boundedliveE2E ไม่มีการข้ามgateด้วยgreenunit tests
