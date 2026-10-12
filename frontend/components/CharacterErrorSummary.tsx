"use client";
import {useEffect,useState} from "react";
import type {EvaluationMode,FieldComparison} from "@/types";
import type {ErrorInsights,InsightScope} from "@/types/evaluation-insights";
import {getErrorInsights} from "@/lib/api";
import {alignmentCounts} from "./CanonicalAlignment";
import SourceCropPreview from "./SourceCropPreview";
const states:Record<string,string>={no_confirmed_gt:"ยังไม่มี Ground Truth ที่ยืนยัน",outdated:"ผลประเมินล้าสมัย — กรุณาคำนวณใหม่",pipeline_failed:"Pipeline ประมวลผลไม่สำเร็จ",alignment_unavailable:"ไม่สามารถสร้าง alignment ที่ตรงกับผลประเมินเดิมได้"};
export default function CharacterErrorSummary({caseId,pipelineId,fieldId,mode,evaluation,unavailable,initiallyOpen=false}:{caseId:string;pipelineId:string;fieldId?:string;mode?:EvaluationMode;evaluation?:FieldComparison|null;unavailable?:string;initiallyOpen?:boolean}){
 const [open,setOpen]=useState(initiallyOpen),[data,setData]=useState<ErrorInsights|null>(null),[error,setError]=useState(""),[character,setCharacter]=useState<string|undefined>(),[all,setAll]=useState(false),[crop,setCrop]=useState<InsightScope|null>(null);
 useEffect(()=>{if(!open||unavailable)return;const controller=new AbortController();let active=true;
 getErrorInsights(caseId,{pipeline_id:pipelineId,field_id:fieldId,mode,character},controller.signal).then(v=>{if(active){setData(v);setError("");}}).catch(e=>{if(active)setError(e instanceof Error?e.message:"โหลดรายละเอียดไม่ได้");});
 return()=>{active=false;controller.abort();};},[caseId,pipelineId,fieldId,mode,character,open,unavailable]);
 const run=data?.pipelines[0],counts=evaluation?.spans?alignmentCounts(evaluation.spans):null;
 const totals=run?.statistics??(counts?{character_edits:counts.substitution+counts.deletion+counts.insertion,...counts}:null);
 return <section aria-label="Character Error Summary" className="mt-2 rounded-lg border border-slate-200 bg-white p-3 text-xs">
 <h3 className="font-semibold">Character Error Summary — สรุปอักขระที่อ่านผิด</h3>
 {unavailable?<p className="mt-2 text-amber-800">{unavailable}</p>:<>
 {totals&&<dl className="my-2 grid grid-cols-2 gap-2">{(["character_edits","substitution","deletion","insertion"] as const).map(k=><div key={k}><dt>{k==="character_edits"?"Total Character Edits":k}</dt><dd className="font-semibold">{totals[k]}</dd></div>)}</dl>}
 {totals?.character_edits===0&&(run?run.evaluated_scopes>0:!!counts)&&<p>ไม่พบข้อผิดพลาดในผลที่ประเมินแล้ว</p>}
 <button className="mt-2 text-indigo-700 underline" aria-expanded={open} onClick={()=>setOpen(v=>!v)}>{open?"ย่อสถิติอักขระ":"ดูสถิติอักขระ"}</button>
 {open&&<div className="mt-3 space-y-3">
 {error&&<p role="alert">{error}</p>}{!data&&!error&&<p role="status">กำลังโหลดรายละเอียด…</p>}
 {run&&<>
 <p className="font-semibold break-words">{run.pipeline_name} · ประเมิน {run.evaluated_scopes}/{run.total_scopes} ส่วน</p>
 {run.scopes.filter(s=>s.state!=="ready").map((s,i)=><p key={i} className="text-amber-800">Field {s.field_index??"Document"}: {states[s.state]??s.state}</p>)}
 {run.status==="error"&&<p>Pipeline ?????????????????</p>}{!run.scopes.length&&<p>ยังไม่มีรายละเอียด Field สำหรับผลนี้</p>}
 <div className="flex flex-wrap gap-2">{run.statistics.characters.slice(0,all?undefined:6).map(c=><button key={c.character} aria-pressed={character===c.character} title={c.code_point} className="rounded border border-slate-300 px-2 py-1 text-left hover:bg-indigo-50 focus-visible:outline-2 focus-visible:outline-indigo-600" onClick={()=>{if(character!==c.character){setData(null);setCharacter(c.character);}}}>
 <span className="font-semibold">{c.display} · {c.name}: {c.total}</span><span className="block text-slate-500">S {c.substitution} / D {c.deletion} / I {c.insertion} · {c.code_point}</span></button>)}</div>
 {run.statistics.characters.length>6&&<button className="text-indigo-700 underline" onClick={()=>setAll(v=>!v)}>{all?"แสดงน้อยลง":"แสดงอักขระทั้งหมด"}</button>}
 {!!run.statistics.confusion_pairs.length&&<p>คู่ที่สับสน: {run.statistics.confusion_pairs.slice(0,5).map(p=>`${p.expected} → ${p.predicted} (${p.count})`).join(", ")}</p>}
 {character&&run.scopes.filter(s=>s.state==="ready").map(s=><div key={s.field_id??"document"} className="space-y-2">
 {s.details.map((e,i)=><article key={i} className="rounded border border-red-100 bg-red-50 p-2 break-words">
 <strong>{run.pipeline_name} · Field {s.field_index??"Document"} · {e.line_number?`บรรทัด ${e.line_number}`:"ไม่สามารถระบุบรรทัดได้"}</strong>
 <p>{e.error_type}: ควรเป็น {e.ground_truth_unit??"∅"} · อ่านได้ {e.ocr_unit??"∅"}</p><p className="whitespace-pre-wrap">GT: {e.ground_truth_excerpt}</p><p className="whitespace-pre-wrap">OCR: {e.ocr_excerpt}</p>
 <button className="mt-1 text-indigo-700 underline" onClick={()=>setCrop(s)}>ดูภาพต้นฉบับ (Field Crop)</button>
 </article>)}{s.details_truncated&&<p>แสดงตัวอย่างสูงสุด 50 รายการ · ดูรายละเอียดทั้งหมดใน Export Evaluation Report</p>}
 </div>)}
 </>}
 </div>}
 </>}
 {crop&&data&&<SourceCropPreview documentId={data.document_id} page={data.page_number} roi={crop.roi} onClose={()=>setCrop(null)}/>}
 </section>;
}
