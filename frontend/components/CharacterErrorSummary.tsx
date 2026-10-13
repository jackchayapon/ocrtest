"use client";
import {useEffect,useState} from "react";
import type {EvaluationMode,FieldComparison} from "@/types";
import type {ErrorInsights} from "@/types/evaluation-insights";
import {getErrorInsights} from "@/lib/api";
import {alignmentCounts} from "./CanonicalAlignment";
import FieldErrorDetails from "./FieldErrorDetails";
const states:Record<string,string>={no_confirmed_gt:"ยังไม่มี Ground Truth ที่ยืนยัน",outdated:"ผลประเมินล้าสมัย — กรุณาคำนวณใหม่",pipeline_failed:"Pipeline ประมวลผลไม่สำเร็จ",alignment_unavailable:"ไม่สามารถสร้าง alignment ที่ตรงกับผลประเมินเดิมได้"};
export default function CharacterErrorSummary({caseId,pipelineId,fieldId,mode,evaluation,unavailable,initiallyOpen=false}:{caseId:string;pipelineId:string;fieldId?:string;mode?:EvaluationMode;evaluation?:FieldComparison|null;unavailable?:string;initiallyOpen?:boolean}){
 const [open,setOpen]=useState(initiallyOpen),[data,setData]=useState<ErrorInsights|null>(null),[error,setError]=useState(""),[character,setCharacter]=useState<string|undefined>(),[all,setAll]=useState(false);
 useEffect(()=>{if(!open||unavailable)return;const controller=new AbortController();let active=true;
 getErrorInsights(caseId,{pipeline_id:pipelineId,field_id:fieldId,mode,character},controller.signal).then(v=>{if(active){setData(v);setError("");}}).catch(e=>{if(active)setError(e instanceof Error?e.message:"โหลดรายละเอียดไม่ได้");});
 return()=>{active=false;controller.abort();};},[caseId,pipelineId,fieldId,mode,character,open,unavailable]);
 const run=data?.pipelines[0],counts=evaluation?.spans?alignmentCounts(evaluation.spans):null;
 const totals=run?.statistics??(counts?{character_edits:counts.substitution+counts.deletion+counts.insertion,...counts}:null);
 return <section aria-label="สรุปข้อผิดพลาดในการอ่านตัวอักษร" className="mt-2 rounded-lg border border-slate-200 bg-white p-4 text-base leading-7">
 <h3 className="font-semibold">สรุปข้อผิดพลาดในการอ่านตัวอักษร</h3>
 {unavailable?<p className="mt-2 text-amber-800">{unavailable}</p>:<>
 {totals&&<dl className="my-2 grid grid-cols-2 gap-2">{(["character_edits","substitution","deletion","insertion"] as const).map(k=><div key={k}><dt>{({character_edits:"อักขระที่ผิดพลาดทั้งหมด",substitution:"อ่านผิด",deletion:"อ่านขาดหาย",insertion:"อ่านเกิน"})[k]}</dt><dd className="font-semibold">{totals[k]}</dd></div>)}</dl>}
 {totals?.character_edits===0&&(run?run.evaluated_scopes>0:!!counts)&&<p>ไม่พบข้อผิดพลาดในการอ่านตัวอักษร</p>}
 <button className="mt-2 text-indigo-700 underline" aria-expanded={open} onClick={()=>setOpen(v=>!v)}>{open?"ย่อสถิติอักขระ":"ดูสถิติอักขระ"}</button>
 {open&&<div className="mt-3 space-y-3">
 {error&&<p role="alert">{error}</p>}{!data&&!error&&<p role="status">กำลังโหลดรายละเอียด…</p>}
 {run&&<>
 <p className="text-slate-500">CER = อักขระ · WER = คำ</p><p>CER {run.metrics?.cer==null?"—":(run.metrics.cer*100).toFixed(2)+"%"} · WER {run.metrics?.wer==null?"—":(run.metrics.wer*100).toFixed(2)+"%"}</p><p className="font-semibold break-words">{run.pipeline_name} · ประเมิน {run.evaluated_scopes}/{run.total_scopes} ส่วน</p>
 {run.scopes.filter(s=>s.state!=="ready").map((s,i)=><p key={i} className="text-amber-800">Field {s.field_index??"ทั้งเอกสาร"}: {states[s.state]??s.state}</p>)}
 {run.status==="error"&&<p>Pipeline ?????????????????</p>}{!run.scopes.length&&<p>ยังไม่มีรายละเอียด Field สำหรับผลนี้</p>}
 <div className="flex flex-wrap gap-2">{run.statistics.characters.slice(0,all?undefined:6).map(c=><button key={c.character} aria-pressed={character===c.character} title={c.code_point} className="rounded border border-slate-300 px-2 py-1 text-left hover:bg-indigo-50 focus-visible:outline-2 focus-visible:outline-indigo-600" onClick={()=>{if(character!==c.character){setData(null);setCharacter(c.character);}}}>
 <span className="font-semibold">{c.display} · {c.name}: {c.total}</span><span className="block text-slate-500">อ่านผิด {c.substitution} / อ่านขาดหาย {c.deletion} / อ่านเกิน {c.insertion} · {c.code_point}</span></button>)}</div>
 {run.statistics.characters.length>6&&<button className="text-indigo-700 underline" onClick={()=>setAll(v=>!v)}>{all?"แสดงน้อยลง":"แสดงอักขระทั้งหมด"}</button>}
 {!!run.statistics.confusion_pairs.length&&<p>คู่ตัวอักษรที่อ่านสับสน: {run.statistics.confusion_pairs.slice(0,5).map(p=>`${p.expected} → ${p.predicted} (${p.count})`).join(", ")}</p>}
 {!character&&run.scopes.filter(s=>s.state==="ready").map(s=><div key={s.field_id??"document"}>{s.explanations?.map((text,i)=><p key={i}>{text}</p>)}</div>)}
 {character&&data&&<FieldErrorDetails key={`${caseId}:${pipelineId}:${mode}:${character}`} data={data} run={run}/>}
 </>}
 </div>}
 </>}
 </section>;
}
