"use client";
import {useState} from "react";
import CharacterErrorSummary from "./CharacterErrorSummary";
import {exportEvaluationReport,exportEvaluationExcel} from "@/lib/api";
const evaluationDefault:AnalysisMode={highlight:true,details:false};
import AnalysisMenu, {type AnalysisMode} from "./AnalysisMenu";
import InteractiveErrorText from "./InteractiveErrorText";
import {Expand} from "lucide-react";
import PipelineVisibilityFilter from "./PipelineVisibilityFilter";
import PipelineResultPreview from "./PipelineResultPreview";
import type {EvaluationMode, GlobalField, PipelineRun, TestCase} from "@/types";
import {pipelineLabel} from "@/lib/i18n/th";

const pct=(n:number|null|undefined)=>n==null?"—":`${(n*100).toFixed(2)}%`;
type Props={fields:GlobalField[];saved:TestCase;runs:PipelineRun[];mode:EvaluationMode;documentGT:string;onMode:(mode:EvaluationMode)=>void;onEdit:()=>void;busy:boolean};

export default function GlobalFieldEvaluation({fields,saved,runs,mode,documentGT,onMode,onEdit,busy}:Props){
 const [exporting,setExporting]=useState(false),[exportError,setExportError]=useState("");
 const [expanded,setExpanded]=useState<{run:PipelineRun;fieldId:string|null}|null>(null);
 const [hiddenPipelines,setHiddenPipelines]=useState<string[]>([]);
 const [analysisPipelines,setAnalysisPipelines]=useState<Record<string,AnalysisMode>>({});
 const visibleRuns=runs.filter(run=>!hiddenPipelines.includes(run.pipeline_id));
 const whole=mode==="whole_document";
 const rows=whole?[{id:"document",name:"Whole Field",gt:documentGT,dirty:documentGT!==(saved.ground_truth_raw??"")}]:[...fields].sort((a,b)=>a.field_index-b.field_index).map(f=>({id:f.id,name:`Field ${String(f.field_index).padStart(2,"0")}`,gt:f.ground_truth_raw??"",dirty:(f.ground_truth_raw??"")!==(saved.global_fields?.find(s=>s.id===f.id)?.ground_truth_raw??"")}));
 return <section aria-label="Evaluation Results" className="panel min-w-0">
  <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 p-5">
   <div><h2>ผลประเมินและเปรียบเทียบ</h2><p className="mt-1 text-sm text-slate-500">ข้อความจริงตรึงด้านซ้าย · เลื่อนแนวนอนเพื่อเทียบ Pipeline และเลื่อนลงเพื่อดูทุก Field</p></div>
   {exportError&&<p role="alert">{exportError}</p>}
   <button className="button secondary" disabled={busy} onClick={onEdit}>กลับไปแก้ Ground Truth</button>
   <div className="flex w-full flex-wrap items-center gap-2" aria-label="Evaluation mode">{(["whole_document","per_field"] as const).map(m=><button key={m} disabled={busy} aria-pressed={m===mode} className={`button ${mode===m?"primary":"secondary"}`} onClick={()=>onMode(m)}>{m==="whole_document"?"Whole Field":"Sub-fields"}</button>)}<PipelineVisibilityFilter runs={runs} hidden={hiddenPipelines} onApply={setHiddenPipelines}/><details className="relative ml-auto shrink-0" data-testid="export-menu" onKeyDown={e=>{if(e.key==="Escape"){e.currentTarget.open=false;e.currentTarget.querySelector("summary")?.focus();}}}>
<summary className="button primary cursor-pointer list-none">{exporting?"กำลังสร้างรายงาน…":"ส่งออก Excel ▾"}</summary>
<div className="absolute right-0 top-full z-40 mt-2 flex w-72 max-w-[85vw] flex-col gap-2 rounded-lg border border-slate-200 bg-white p-3 shadow-lg">
   <button className="button primary" disabled={busy||exporting||!visibleRuns.length||rows.some(r=>r.dirty)||visibleRuns.some(run=>whole?run.status==="success"&&!run.document_evaluation:fields.some(f=>{const prediction=run.fields?.find(p=>p.global_field_id===f.id);return prediction?.status==="success"&&!prediction.evaluation;}))} onClick={async()=>{
    setExporting(true);setExportError("");
    try{await exportEvaluationExcel(saved.id,{mode,pipeline_ids:visibleRuns.map(r=>r.pipeline_id),run_ids:visibleRuns.map(r=>r.id),field_ids:whole?[]:rows.map(r=>r.id),revision:saved.updated_at});}
    catch(e){setExportError(e instanceof Error?e.message:"ส่งออก Excel ไม่สำเร็จ");}
    finally{setExporting(false);}
   }}>เอกสารนี้ — Excel (.xlsx)</button>
   <button className="button secondary" disabled={busy||exporting||rows.some(r=>r.dirty)} onClick={async()=>{setExporting(true);setExportError("");try{await exportEvaluationReport(saved.id,mode);}catch(e){setExportError(e instanceof Error?e.message:"ส่งออกรายงานไม่สำเร็จ");}finally{setExporting(false);}}}>{exporting?"กำลังสร้างรายงาน…":"ส่งออกรายงาน ZIP (ทุก Pipeline)"}</button>
</div></details></div>
  </div>
  {!!runs.length&&!visibleRuns.length&&<p className="p-4 text-sm text-slate-500">เลือก Pipeline เพื่อแสดงผลเปรียบเทียบ</p>}
  <div role="region" aria-label="ตารางเปรียบเทียบ Pipeline" tabIndex={0} data-testid="comparison-scroll" className="max-h-[75vh] overflow-auto focus-visible:outline-2 focus-visible:outline-indigo-500">
   <table className="w-full table-fixed border-separate border-spacing-0 text-left text-sm" style={{minWidth:`calc(clamp(140px, 30vw, 280px) + ${visibleRuns.length*280}px)`}}>
    <colgroup><col style={{width:"clamp(140px, 30vw, 280px)"}}/>{visibleRuns.map(r=><col key={r.id} style={{width:280}}/>)}</colgroup>
    <thead><tr><th scope="col" className="sticky left-0 top-0 z-30 border-b border-r border-sky-200 bg-sky-100 p-3">ข้อความจริง (Ground Truth)</th>{visibleRuns.map(run=><th key={run.id} scope="col" className="sticky top-0 z-20 border-b border-r border-slate-300 bg-slate-100 p-3 break-words"><div className="flex flex-wrap items-center justify-between gap-2"><span>{pipelineLabel(run.pipeline_id,run.pipeline_name)}</span><div className="flex shrink-0 items-center gap-1"><AnalysisMenu name={pipelineLabel(run.pipeline_id,run.pipeline_name)} value={analysisPipelines[run.pipeline_id]??evaluationDefault} onChange={value=>setAnalysisPipelines(old=>({...old,[run.pipeline_id]:value}))}/><button type="button" className="rounded p-2 hover:bg-indigo-100" aria-label={`Expand ${pipelineLabel(run.pipeline_id,run.pipeline_name)}`} onClick={()=>setExpanded({run,fieldId:null})}><Expand size={16}/></button></div></div></th>)}</tr></thead>
    {rows.map(row=><tbody key={row.id} data-testid={`comparison-row-${row.id}`}><tr data-testid="comparison-text-row">
     <th scope="row" className="sticky left-0 z-10 border-b border-r border-sky-200 bg-sky-50 p-3 align-top font-normal shadow-[2px_0_4px_-2px_#94a3b8]">
      <section data-testid="gt-pane" tabIndex={0} className={`space-y-2 pr-2 ${whole?"min-h-64":"min-h-32"}`}>
      <p className="font-semibold text-sky-900">{row.name}</p><p data-testid="confirmed-global-gt" className="whitespace-pre-wrap break-words leading-relaxed">{row.gt||"ยังไม่ได้กรอก Ground Truth"}</p>
      {row.dirty&&<p className="mt-3 text-xs text-amber-800">แก้ไข GT แล้ว — ต้องยืนยันคำนวณใหม่</p>}
      </section>
     </th>
     {visibleRuns.map(run=>{
      const field=run.fields?.find(f=>f.global_field_id===row.id);
      const failed=whole?run.status==="error":field?.status==="error";
      const evaluation=row.dirty||failed?null:whole?run.document_evaluation:field?.evaluation;
      const analysis=analysisPipelines[run.pipeline_id]??evaluationDefault;
      return <td key={run.id} data-testid={`global-result-${run.pipeline_id}`} className="border-b border-r border-slate-200 p-3 align-top">
       <section aria-label="Extracted Text" data-testid="prediction-pane" tabIndex={0} className={`space-y-2 pr-2 ${whole?"min-h-64":"min-h-32"}`}>
       <h3 className="text-sm font-semibold text-slate-500" title={analysis.highlight?"สีเขียว: ถูก · กดสีแดงเพื่อดูข้อความที่ผิด เกิน หรือขาด":undefined}>ข้อความที่ OCR อ่านได้{analysis.highlight&&<span className="ml-2 text-xs font-normal text-green-700">HIGHLIGHT</span>}</h3>
       {failed&&<p role="alert" className="mb-3 text-amber-800">บริการ OCR ยังไม่พร้อมใช้งาน</p>}
       {!whole&&!field&&!failed&&<p className="mb-3 text-slate-500">ไม่มีผลลัพธ์สำหรับ Field นี้</p>}
       {analysis.highlight&&evaluation?<InteractiveErrorText evaluation={evaluation} groundTruth={row.gt}/>:<p data-testid="global-prediction" className="whitespace-pre-wrap break-words leading-relaxed">{(whole?run.final_text:field?.ocr_text)||"(ไม่พบข้อความ)"}</p>}

       </section>

      </td>;
     })}
    </tr><tr data-testid="comparison-metrics-row">
     <td className="sticky left-0 z-10 border-b border-r border-sky-200 bg-sky-50 p-3 align-top text-xs text-slate-500">CER / WER</td>
     {visibleRuns.map(run=>{
      const field=run.fields?.find(f=>f.global_field_id===row.id);
      const failed=whole?run.status==="error":field?.status==="error";
      const evaluation=row.dirty||failed?null:whole?run.document_evaluation:field?.evaluation;
      const analysis=analysisPipelines[run.pipeline_id]??evaluationDefault;
      return <td key={run.id} data-testid={`global-metrics-${run.pipeline_id}`} className="border-b border-r border-slate-200 p-3 align-top">
       <section aria-label="Metrics" data-testid={evaluation?"global-evaluation":"not-evaluated"} className="my-4 rounded-lg bg-slate-50 p-3">
        <dl className="grid grid-cols-2 gap-2">{[["Confidence",pct(whole?run.confidence:field?.confidence)],["CER",pct(evaluation?.cer)],["WER",pct(evaluation?.wer)],["Exact Match",evaluation?(evaluation.exact_match?"✓ Yes":"✕ No"):"—"]].map(([label,value])=><div key={label}><dt className="text-xs text-slate-500">{label}</dt><dd className="font-semibold">{value}</dd></div>)}</dl>
        {!evaluation&&<p className="mt-2 text-xs text-slate-500">ยังไม่ประเมิน — กลับไปกรอก GT แล้วยืนยันเพื่อคำนวณ</p>}
       </section>
       <CharacterErrorSummary key={JSON.stringify([run.id,row.id,mode,evaluation,row.gt])} caseId={saved.id} pipelineId={run.pipeline_id} fieldId={whole?undefined:row.id} mode={mode} evaluation={evaluation} expanded={analysis.details} onExpandedChange={details=>setAnalysisPipelines(old=>({...old,[run.pipeline_id]:{...(old[run.pipeline_id]??evaluationDefault),details}}))}
        unavailable={row.dirty?"แก้ไข GT แล้ว — ต้องยืนยันคำนวณใหม่":failed?"Pipeline ประมวลผลไม่สำเร็จ":!evaluation?"ยังไม่มี GT ที่ยืนยันหรือผลประเมินล้าสมัย":undefined}/>
      </td>;
     })}
    </tr></tbody>)}
   </table>
   {!rows.length&&<p className="p-5 text-slate-500">ไม่มี Field สำหรับเปรียบเทียบ</p>}
  </div>
  {!runs.length&&<p className="p-5 text-slate-500">ยังไม่มีผลลัพธ์ Pipeline</p>}
 {expanded&&<PipelineResultPreview run={expanded.run} fieldId={expanded.fieldId} saved={saved} fields={fields} documentGT={documentGT} onClose={()=>setExpanded(null)}/>}
 </section>;
}
