"use client";

import Link from "next/link";
import {LoaderCircle} from "lucide-react";
import {useEffect,useRef,useState} from "react";
import {APIError,createOCRJob,getCaseOCRJob,getOCRJob,type OCRJob} from "@/lib/api";

const active=(job:OCRJob)=>job.status==="queued"||job.status==="running";

export default function OCRJobRunner({caseId,pipelines,names,onCompleted,onBusy,resultsUrl}:{
 caseId:string;pipelines:string[];names:Record<string,string>;onCompleted:()=>void;onBusy:(busy:boolean)=>void;resultsUrl:string;
}){
 const [job,setJob]=useState<OCRJob|null>(null),[checking,setChecking]=useState(true),[submitting,setSubmitting]=useState(false),[error,setError]=useState("");
 const [clock,setClock]=useState(()=>Date.now());
 const pending=useRef(false),callbacks=useRef({onCompleted,onBusy});
 const activeId=job&&active(job)?job.job_id:null;
 useEffect(()=>{if(!activeId)return;const timer=setInterval(()=>setClock(Date.now()),1000);return()=>clearInterval(timer);},[activeId]);
 useEffect(()=>{callbacks.current={onCompleted,onBusy};},[onCompleted,onBusy]);
 const storageKey=`ocrlab-job:${caseId}`;
 useEffect(()=>{
  const controller=new AbortController();
  getCaseOCRJob(caseId,controller.signal).then(value=>{
   if(controller.signal.aborted)return;
   if(value&&(active(value)||localStorage.getItem(storageKey)===value.job_id))setJob(value);
   setChecking(false);
  }).catch(()=>{if(!controller.signal.aborted){setError("ตรวจสอบงานเดิมไม่ได้ กรุณาลองตรวจสอบอีกครั้งก่อนเริ่มงานใหม่");setChecking(false);}});
  return()=>controller.abort();
 },[caseId,storageKey]);
 useEffect(()=>{callbacks.current.onBusy(checking||submitting||!!job&&active(job));return()=>callbacks.current.onBusy(false);},[checking,submitting,job]);
 useEffect(()=>{
  if(!job)return;
  if(!active(job)){
   localStorage.removeItem(storageKey);
   if(job.status==="completed")callbacks.current.onCompleted();
   return;
  }
  const controller=new AbortController();let timer:ReturnType<typeof setTimeout>;let failures=0;
  async function poll(){
   try{const next=await getOCRJob(job!.job_id,controller.signal);if(controller.signal.aborted)return;setJob(next);setClock(Date.now());setError("");failures=0;}
   catch(e){if(controller.signal.aborted)return;if(e instanceof APIError&&e.status>=400&&e.status<500){setError(e.status===404?"ไม่พบงาน OCR เดิม กรุณาตรวจสอบประวัติ":e.message);localStorage.removeItem(storageKey);setJob(null);return;}failures++;setError("ไม่สามารถตรวจสอบสถานะได้ชั่วคราว ระบบจะลองเชื่อมต่อเพื่อตรวจสอบงานเดิมอีกครั้ง");}
   if(!controller.signal.aborted)timer=setTimeout(poll,Math.min(15000,2500*(failures+1)));
  }
  timer=setTimeout(poll,2500);
  return()=>{controller.abort();clearTimeout(timer);};
 },[job,storageKey]);
 async function start(){
  if(pending.current)return;pending.current=true;setSubmitting(true);setError("");
  const requestKey=`${storageKey}:request:${JSON.stringify(pipelines)}`;
  const key=localStorage.getItem(requestKey)||crypto.randomUUID();localStorage.setItem(requestKey,key);
  try{const next=await createOCRJob(caseId,pipelines,key);localStorage.setItem(storageKey,next.job_id);localStorage.removeItem(requestKey);setJob(next);}
  catch(e){setError(e instanceof Error?e.message:"ส่งงานไม่สำเร็จ กรุณาตรวจสอบการเชื่อมต่อ");}
  finally{pending.current=false;setSubmitting(false);}
 }
 const elapsed=Math.max(0,Math.floor((clock-Date.parse(job?.started_at||job?.created_at||new Date(clock).toISOString()))/1000));
 const busy=checking||submitting||!!job&&active(job);
 return <section className="space-y-3" aria-label="สถานะงาน OCR">
  {error&&<p role="alert" className="error-banner">{error}</p>}
  <button aria-busy={busy} className="button primary" disabled={busy||!pipelines.length} onClick={()=>void start()}>{busy?<><LoaderCircle aria-hidden="true" data-testid="ocr-spinner" className="h-4 w-4 animate-spin"/>กำลังรัน OCR...</>:"Run OCR"}</button>
  {job&&<div role="status" className="rounded-lg border border-sky-200 bg-sky-50 p-4 space-y-2" data-testid="ocr-job-progress">
   <p>{active(job)?"กำลังประมวลผล OCR":job.status==="completed"?"ประมวลผล OCR สำเร็จ":job.status==="partial_success"?"OCR เสร็จสิ้น แต่มีบาง Pipeline ที่ไม่สำเร็จ":"งาน OCR ไม่สำเร็จ"}</p>
   <progress aria-label="ความคืบหน้า OCR" max={100} value={job.progress_percent} className="w-full"/>
   <p>{job.progress_percent}% · ประมวลผลแล้ว: {job.completed_units} / {job.total_fields*job.total_pipelines} รายการ</p>
   <p>Pipeline ครบแล้ว: {job.completed_pipelines} / {job.total_pipelines} · รายการผิดพลาด: {job.failed_units}</p>
   {job.current_pipeline_id&&<p>Pipeline ที่กำลังทำงาน: {names[job.current_pipeline_id]||job.current_pipeline_id}</p>}
   <p>เวลาที่ผ่านไป: {String(Math.floor(elapsed/60)).padStart(2,"0")}:{String(elapsed%60).padStart(2,"0")}</p>
   {active(job)&&<p className="text-sm">ปิดหรือรีเฟรชหน้านี้ได้ งานเดิมจะถูกติดตามจากเซิร์ฟเวอร์</p>}
   {job.safe_error_message&&<p>{job.safe_error_message}</p>}
   {!active(job)&&<Link className="text-sky-800 underline" href={resultsUrl}>ดูผลลัพธ์และรายละเอียดข้อผิดพลาด</Link>}
  </div>}
 </section>;
}
