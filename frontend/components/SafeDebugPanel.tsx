"use client";
import {useState} from "react";
import type {PipelineRun} from "@/types";

const allowed=["failure_stage","error_code","http_status","request_id","gateway_request_id","gateway_duration_ms","processing_time_ms","crop_width","crop_height"];
export default function SafeDebugPanel({caseId,runs}:{caseId:string;runs:PipelineRun[]}){
 const [open,setOpen]=useState(false),[jobId,setJobId]=useState<string|null>(null);
 return <section className="rounded-lg border border-slate-200 p-3 text-xs">
  <button type="button" className="button secondary" aria-pressed={open} onClick={()=>{setOpen(v=>!v);try{setJobId(localStorage.getItem(`ocrlab-job:${caseId}`));}catch{/* Optional local reference only. */}}}>{open?"ปิด":"เปิด"} Debug Mode</button>
  {open&&<div className="mt-2 space-y-2" data-testid="safe-debug"><p>ข้อมูลเทคนิคที่อนุญาตให้แสดงเท่านั้น · ระบบยังไม่มี login/roles ปุ่มนี้ไม่ใช่การควบคุมสิทธิ์ และไม่เรียก OCR เพิ่ม</p>{jobId&&/^[a-f0-9-]{36}$/i.test(jobId)&&<p>Job ID: {jobId}</p>}{runs.map(run=><details key={run.id}><summary>Pipeline: {run.pipeline_id}</summary>{run.fields?.map(field=><div key={field.id} className="mt-2 break-all"><p>Field ID: {field.global_field_id??field.id}</p>{allowed.map(key=>{const value=field.diagnostics?.[key];return (typeof value==="number"||typeof value==="string"&&/^[A-Za-z0-9_.:-]{1,150}$/.test(value))?<p key={key}>{key}: {String(value)}</p>:null;})}</div>)}</details>)}</div>}
 </section>;
}
