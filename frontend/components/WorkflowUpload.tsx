"use client";
import {useEffect,useState} from "react";
import {useRouter} from "next/navigation";
import type {Document} from "@/types";
import * as api from "@/lib/api";
import DocumentUploader from "./DocumentUploader";
import DocumentTypePicker from "./DocumentTypePicker";
import WorkflowSteps,{workflowUrl} from "./WorkflowSteps";
import {PageHeader} from "./ConsoleUI";
import {userError} from "@/lib/i18n/th";

export default function WorkflowUpload(){
 const router=useRouter();const [doc,setDoc]=useState<Document|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState("");
 const [limits,setLimits]=useState<Awaited<ReturnType<typeof api.getUploadConfig>>|null>(null);
 const [documentType,setDocumentType]=useState("");
 useEffect(()=>{let alive=true;api.getUploadConfig().then(c=>{if(alive)setLimits(c);}).catch(()=>{if(alive)setError("ไม่สามารถตรวจสอบขีดจำกัดการอัปโหลด กรุณารีเฟรช / Upload limits unavailable");});
  const q=new URLSearchParams(window.location.search),id=q.get('document');
  if(id)api.getDocumentPage(id,q.has('page')?Number(q.get('page')):undefined).then(d=>{if(alive){setDoc(d);setDocumentType(d.document_type_id||"");}}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[]);
 async function act(fn:()=>Promise<void>){setBusy(true);setError("");try{await fn();}catch(e){setError(userError(e instanceof Error?e.message:"ดำเนินการไม่สำเร็จ"));}finally{setBusy(false);}}
 function remember(d:Document){setDoc(d);window.history.replaceState(null,"",`/?document=${d.id}${d.document_type==="pdf"?`&page=${d.page_number??1}`:""}`);}
 const upload=(file:File)=>void act(async()=>{if(!limits)throw new Error("กำลังตรวจสอบขีดจำกัดการอัปโหลด");if(file.size>limits.max_upload_mb*1024*1024)throw new Error(`ไฟล์เกิน ${limits.max_upload_mb} MiB / Upload too large`);remember(await api.uploadDocument(file,documentType));});
 return <div className="page-stack" data-testid="workflow-upload"><PageHeader title="Upload Document" description="เลือกเอกสารและหน้าที่ต้องการทดสอบ"/><WorkflowSteps stage="upload"/>
 {error&&<div role="alert" className="error-banner">{error}</div>}
 {limits&&<p role="note" data-testid="workload-limits" className="text-sm text-slate-600">รองรับภาพไม่เกิน {limits.max_image_pixels/1_000_000} MP · ด้านละไม่เกิน {limits.max_image_dimension} px · ไฟล์ไม่เกิน {limits.max_upload_mb} MiB · PDF ไม่เกิน {limits.max_pdf_pages} หน้า ที่ {limits.pdf_render_dpi} DPI และจำกัดพิกเซลต่อหน้าเท่ากับภาพ · OCR ทีละ 1 งาน ไม่เกิน {limits.max_job_fields} Fields / {limits.max_job_pipelines} Pipelines โดย Fields × Pipelines ไม่เกิน {limits.max_job_units??24} · ไม่เกิน {limits.max_detection_regions??128} DET regions และ {limits.max_ocr_text_characters??32768} ตัวอักษร OCR ต่อ Field ไม่ตัดผลลัพธ์ให้สั้นลง · คิวรวมไม่เกิน {limits.ocr_queue_capacity} งาน · ไม่ย่อภาพอัตโนมัติ / Supported input limits; oversized inputs are rejected.</p>}
 <section className="panel panel-body space-y-5" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();const f=e.dataTransfer.files[0];if(f&&!busy)upload(f);}}>
 <DocumentTypePicker value={documentType} onArchive={()=>setDocumentType("")} onChange={id=>void act(async()=>{setDocumentType(id);if(doc)remember(await api.updateDocumentType(doc.id,id,doc.page_number));})} disabled={busy}/>
 <div className="rounded-xl border-2 border-dashed p-8 text-center space-y-4"><p>ลากภาพหรือ PDF มาวางที่นี่</p><DocumentUploader onUpload={upload} disabled={busy} primary/><button className="button secondary ml-2" disabled={busy} onClick={()=>void act(async()=>remember(await api.uploadDocument(await api.loadSample(),documentType)))}>ใช้เอกสารตัวอย่าง</button></div>
 {doc&&<><div className="flex flex-wrap items-center justify-between gap-4"><p className="break-words min-w-0">{doc.filename} · {doc.document_type_name||"ไม่ระบุประเภท"}</p>{doc.document_type==="pdf"&&<label>เลือกหน้า PDF <select className="select" disabled={busy} value={doc.page_number??1} onChange={e=>void act(async()=>remember(await api.getDocumentPage(doc.id,Number(e.target.value))))}>{Array.from({length:doc.page_count},(_,i)=><option key={i} value={i+1}>หน้า {i+1}</option>)}</select></label>}</div>
 {/* Source preview has no editable/model overlays. */}
 {/* eslint-disable-next-line @next/next/no-img-element */}
 <img src={api.assetUrl(doc.image_url)} alt="เอกสารที่อัปโหลด" className="max-h-[55vh] max-w-full mx-auto object-contain"/>
 <div className="flex justify-end"><button className="button primary" disabled={busy} onClick={()=>void act(async()=>{
  const c=await api.createTestCase({workflow:"global",document_id:doc.id,page_number:doc.page_number,roi:null,ground_truth_raw:null,category_codes:[]});router.push(workflowUrl(c.id,"layout"));
 })}>ถัดไป: จัดการ Layout</button></div></>}
 {busy&&<p role="status">กำลังดำเนินการ…</p>}
 </section></div>;
}
