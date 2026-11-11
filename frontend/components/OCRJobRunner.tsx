"use client";

import Link from "next/link";
import {LoaderCircle} from "lucide-react";
import {useEffect,useRef,useState} from "react";
import {APIError,createOCRJob,getCaseOCRJob,getOCRJob,getOCRJobResults,type OCRJob} from "@/lib/api";
import {jobElapsedSeconds} from "@/lib/job-timing";
import {jobWasOpened,rememberJob} from "@/lib/job-navigation";

const active=(job:OCRJob)=>job.status==="queued"||job.status==="running";
const RESULT_ATTEMPTS=6,RESULT_DEADLINE_MS=30_000,RESULT_RECHECK_MS=5_000;

export default function OCRJobRunner({caseId,pipelines,names,onCompleted,onBusy,resultsUrl}:{
 caseId:string;pipelines:string[];names:Record<string,string>;onCompleted:(job:OCRJob)=>void;onBusy:(busy:boolean)=>void;resultsUrl:string;
}){
 const [job,setJob]=useState<OCRJob|null>(null),[checking,setChecking]=useState(true),[submitting,setSubmitting]=useState(false),[error,setError]=useState("");
 const [clock,setClock]=useState(()=>Date.now());
 const [verifying,setVerifying]=useState(false),[verification,setVerification]=useState(0);
 const pending=useRef(false),callbacks=useRef({onCompleted,onBusy});
 const navigated=useRef<string|null>(null);
 const pendingKeys=useRef(new Map<string,string>());
 const activeId=job&&active(job)?job.job_id:null;
 useEffect(()=>{if(!activeId)return;const timer=setInterval(()=>setClock(Date.now()),1000);return()=>clearInterval(timer);},[activeId]);
 useEffect(()=>{callbacks.current={onCompleted,onBusy};},[onCompleted,onBusy]);
 const storageKey=`ocrlab-job:${caseId}`;
 useEffect(()=>{
  const controller=new AbortController();
  getCaseOCRJob(caseId,controller.signal).then(value=>{
   if(controller.signal.aborted)return;
   if(value){rememberJob(caseId,value.job_id);setJob(value);}
   setChecking(false);
  }).catch(()=>{if(!controller.signal.aborted){setError("ตรวจสอบงานเดิมไม่ได้ กรุณาลองตรวจสอบอีกครั้งก่อนเริ่มงานใหม่");setChecking(false);}});
  return()=>controller.abort();
 },[caseId,storageKey]);
 const busy=checking||submitting||verifying||!!job&&active(job);
 useEffect(()=>{callbacks.current.onBusy(busy);},[busy]);
 useEffect(()=>()=>callbacks.current.onBusy(false),[]);
 useEffect(()=>{
  if(!job)return;
  if(!active(job)){
   return;
  }
  const controller=new AbortController();let timer:ReturnType<typeof setTimeout>;let failures=0;
  async function poll(){
   try{const next=await getOCRJob(job!.job_id,controller.signal);if(controller.signal.aborted)return;setJob(next);setClock(Date.now());setError("");failures=0;}
   catch(e){if(controller.signal.aborted)return;if(e instanceof APIError&&e.status>=400&&e.status<500){setError(e.status===404?"ไม่พบงาน OCR เดิม กรุณาตรวจสอบประวัติ":e.message);setJob(null);return;}failures++;setError("ไม่สามารถตรวจสอบสถานะได้ชั่วคราว ระบบจะลองเชื่อมต่อเพื่อตรวจสอบงานเดิมอีกครั้ง");}
   if(!controller.signal.aborted)timer=setTimeout(poll,Math.min(15000,2500*(failures+1)));
  }
  timer=setTimeout(poll,2500);
  return()=>{controller.abort();clearTimeout(timer);};
 },[job,storageKey]);
 useEffect(()=>{
  if(!job||!["completed","partial_success"].includes(job.status)||navigated.current===job.job_id)return;
  if(!verification&&jobWasOpened(caseId,job.job_id))return;
  const controller=new AbortController();let cancelled=false,finished=false,attempts=0;
  let timer:ReturnType<typeof setTimeout>;
  const stop=(message:string)=>{finished=true;clearTimeout(timer);clearTimeout(deadline);controller.abort();setVerifying(false);setError(message);};
  const deadline=setTimeout(()=>stop("หยุดตรวจผลอัตโนมัติแล้ว ยังยืนยันผล OCR ไม่ได้ กดตรวจผลอีกครั้งหรือเปิดรายละเอียด งานเดิมยังถูกเก็บไว้"),RESULT_DEADLINE_MS);
  function recheck(message:string){
   if(attempts>=RESULT_ATTEMPTS){stop("หยุดตรวจผลอัตโนมัติแล้ว ยังยืนยันผล OCR ไม่ได้ กดตรวจผลอีกครั้งหรือเปิดรายละเอียด งานเดิมยังถูกเก็บไว้");return;}
   setError(message);timer=setTimeout(verify,RESULT_RECHECK_MS);
  }
  async function verify(){
   if(cancelled||finished)return;
   attempts++;setVerifying(true);
   rememberJob(caseId,job!.job_id);
   try{
    const result=await getOCRJobResults(job!.job_id,controller.signal);
    if(cancelled||finished)return;
    const usable=result.runs.some(r=>r.fields?.length?r.fields.some(f=>f.status==="success"):r.status==="success");
    if(!usable){recheck("งานสิ้นสุดแล้ว แต่ยังไม่พบผล OCR ที่ใช้งานได้ กำลังตรวจผลที่บันทึกอีกครั้ง");return;}
    stop("");
    try{callbacks.current.onCompleted(job!);navigated.current=job!.job_id;}catch{setError("เปิดหน้า Ground Truth ไม่สำเร็จ กรุณาใช้ลิงก์ผลลัพธ์ด้านล่าง งานเดิมยังถูกเก็บไว้");}
   }catch(e){if(!cancelled&&!finished){
    if(e instanceof APIError&&e.status>=400&&e.status<500&&![408,429].includes(e.status)){stop("ไม่สามารถเข้าถึงผล OCR ได้ กรุณาตรวจสอบสิทธิ์หรือลิงก์ผลลัพธ์ก่อนลองอีกครั้ง");return;}
    recheck("ยังโหลดผลที่บันทึกไม่ได้ ระบบจะตรวจสอบงานเดิมอีกครั้ง หรือเปิดผลลัพธ์ด้านล่าง");
   }}
  }
  void verify();return()=>{cancelled=true;controller.abort();clearTimeout(timer);clearTimeout(deadline);};
 },[job,caseId,storageKey,verification]);
 async function start(){
  if(pending.current)return;pending.current=true;setSubmitting(true);setError("");
  const requestKey=`${storageKey}:request:${JSON.stringify(pipelines)}`;
  try{
   let key=pendingKeys.current.get(requestKey);
   // An explicit new run after a known terminal job must not reuse a stale stored key.
   if(!key&&!job)try{key=localStorage.getItem(requestKey)||undefined;}catch{/* Memory preserves retries in this mounted runner. */}
   key??=crypto.randomUUID();pendingKeys.current.set(requestKey,key);
   try{localStorage.setItem(requestKey,key);}catch{/* Optional persistence; never regenerate the in-flight key. */}
   const next=await createOCRJob(caseId,pipelines,key);
   setJob(next);rememberJob(caseId,next.job_id);pendingKeys.current.delete(requestKey);
   try{localStorage.removeItem(requestKey);}catch{/* Server accepted the job; storage cannot turn acceptance into failure. */}
  }
  catch(e){setError(e instanceof Error?e.message:"ส่งงานไม่สำเร็จ กรุณาตรวจสอบการเชื่อมต่อ");}
  finally{pending.current=false;setSubmitting(false);}
 }
 const elapsed=jobElapsedSeconds(job,clock);
 const pipelineIndex=job?.current_pipeline_id?job.pipeline_ids.indexOf(job.current_pipeline_id):-1;
 const ocrDone=!!job&&job.completed_units>=job.total_fields*job.total_pipelines;
 const prefill=job?.status==="running"&&!!job.current_pipeline_id&&pipelineIndex<0;
 return <section className="space-y-3" aria-label="สถานะงาน OCR">
  {error&&<p role="alert" className="error-banner">{error}</p>}
  <button aria-busy={busy} className="button primary" disabled={busy||!pipelines.length} onClick={()=>void start()}>{busy?<><LoaderCircle aria-hidden="true" data-testid="ocr-spinner" className="h-4 w-4 animate-spin"/>{verifying?"กำลังตรวจผลที่บันทึก...":"กำลังรัน OCR..."}</>:job&&!active(job)?"รัน OCR ใหม่ (ประมวลผลซ้ำ)":"Run OCR"}</button>
  {job&&["completed","partial_success"].includes(job.status)&&<button type="button" className="button secondary" disabled={busy} onClick={()=>{navigated.current=null;setVerification(v=>v+1);}}>ตรวจผลอีกครั้ง (ไม่รัน OCR)</button>}
  {job&&<div role="status" className="rounded-lg border border-sky-200 bg-sky-50 p-4 space-y-2" data-testid="ocr-job-progress">
   <p>{verifying?"กำลังเปิดผลลัพธ์ — ตรวจข้อมูลที่บันทึก":job.status==="queued"?"ส่งงานแล้ว — รอ worker รับงาน":prefill?"กำลังเตรียม Ground Truth — งานทั้งหมดยังไม่เสร็จ":job.status==="running"?ocrDone?"อ่าน OCR ครบแล้ว — กำลังเตรียมขั้นตอนถัดไป":"กำลังประมวลผล OCR":job.status==="completed"?"เสร็จสิ้น — OCR และขั้นตอนเตรียมข้อมูลจบแล้ว":job.status==="partial_success"?"งานเสร็จสิ้นบางส่วน — ตรวจรายละเอียดผลที่บันทึก":job.status==="cancelled"?"งาน OCR ถูกยกเลิก":"งาน OCR ไม่สำเร็จ — ตรวจข้อผิดพลาดก่อนลองใหม่"}</p>
   <progress aria-label="ความคืบหน้า OCR (เฉพาะการอ่าน)" max={100} value={job.progress_percent} className="w-full"/>
   <p>{ocrDone?`อ่าน OCR ครบแล้ว ${job.completed_units}/${job.total_fields*job.total_pipelines} รายการ`:`${job.progress_percent}% · ประมวลผลแล้ว: ${job.completed_units} / ${job.total_fields*job.total_pipelines} รายการ`}</p>
   <p>สำเร็จ: {Math.max(0,job.completed_units-job.failed_units)} · ล้มเหลว: {job.failed_units}</p>
   <p>Pipeline ครบแล้ว: {job.completed_pipelines} / {job.total_pipelines} · รายการผิดพลาด: {job.failed_units}</p>
   {job.status==="running"&&job.current_pipeline_id&&<p>{pipelineIndex>=0?`กำลังประมวลผล Pipeline ${pipelineIndex+1}/${job.total_pipelines}`:"กำลังเตรียม Ground Truth"} — Field {job.current_field_index??0}/{job.total_fields}{pipelineIndex>=0&&` · ${names[job.current_pipeline_id]||job.current_pipeline_id}`}</p>}
   <p>เวลาที่ผ่านไป: {elapsed===null?"—":`${String(Math.floor(elapsed/60)).padStart(2,"0")}:${String(elapsed%60).padStart(2,"0")}`}</p>
   {job.updated_at&&<p className="text-xs">สถานะล่าสุด: {new Date(job.updated_at).toLocaleTimeString("th-TH")}</p>}
   {active(job)&&<p className="text-sm">ปิดหรือรีเฟรชหน้านี้ได้ งานเดิมจะถูกติดตามจากเซิร์ฟเวอร์</p>}
   {job.safe_error_message&&<p>{job.safe_error_message}</p>}
   {!active(job)&&<Link className="text-sky-800 underline" href={resultsUrl}>ดูผลลัพธ์และรายละเอียดข้อผิดพลาด</Link>}
  </div>}
 </section>;
}
