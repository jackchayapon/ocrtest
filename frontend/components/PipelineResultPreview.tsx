"use client";
import ErrorAnalysisText from "./ErrorAnalysisText";
import dynamic from "next/dynamic";
import {useEffect,useRef,useState} from "react";
import {ScanLine,X} from "lucide-react";
import type {FieldComparison,GlobalField,PipelineRun,TestCase} from "@/types";
import {assetUrl} from "@/lib/api";
import {pipelineLabel} from "@/lib/i18n/th";
import {resultPreviewBoxes} from "@/lib/result-preview";
const DocumentViewer=dynamic(()=>import("./DocumentViewer"),{ssr:false});
const pct=(n:number|null|undefined)=>n==null?"—":`${(n*100).toFixed(2)}%`;
function ErrorAnalysis({evaluation,groundTruth}:{evaluation:FieldComparison|null|undefined;groundTruth:string}){
 return <details className="text-sm"><summary className="cursor-pointer">Error Analysis</summary>{!evaluation?<p className="mt-2">ยังไม่ประเมิน</p>:evaluation.exact_match?<p className="mt-2 text-emerald-700">ไม่พบข้อผิดพลาด</p>:<ErrorAnalysisText evaluation={evaluation} groundTruth={groundTruth}/>}</details>;
}

export default function PipelineResultPreview({run,fieldId,saved,fields,documentGT,onClose}:{run:PipelineRun;fieldId:string|null;saved:TestCase;fields:GlobalField[];documentGT:string;onClose:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null);
 const [activeField,setActiveField]=useState<string|null>(fieldId);
 const [selected,setSelected]=useState<string|null>(null);
 const predictions=[...(run.fields??[])].filter(f=>!fieldId||f.global_field_id===fieldId).sort((a,b)=>a.field_index-b.field_index);
 const boxes=resultPreviewBoxes(predictions,run.pipeline_id);
 const highlightedBoxIds=selected?[]:resultPreviewBoxes(predictions.filter(f=>f.global_field_id===activeField),run.pipeline_id).map(b=>b.id);
 const title=pipelineLabel(run.pipeline_id,run.pipeline_name);
 useEffect(()=>{const el=dialog.current;el?.showModal();const overflow=document.body.style.overflow;document.body.style.overflow="hidden";return()=>{el?.close();document.body.style.overflow=overflow;};},[]);
 return <dialog ref={dialog} aria-labelledby="pipeline-preview-title" onCancel={onClose} className="fixed inset-0 m-auto h-[94dvh] max-h-none w-[96vw] max-w-none overflow-hidden rounded-xl border border-slate-200 bg-slate-50 p-0 text-slate-800 shadow-xl backdrop:bg-slate-950/50">
  <div className="flex h-full flex-col">
   <header className="flex shrink-0 items-center justify-between gap-3 border-b bg-white p-4"><div><h2 id="pipeline-preview-title">{title}{fieldId?` · Field ${String(fields.find(f=>f.id===fieldId)?.field_index??"").padStart(2,"0")}`:" · ทุก Field"}</h2><p className="text-xs text-slate-500">ผลที่บันทึกไว้ · กรอบ DET จากโมเดล · ไม่มีการรัน OCR เพิ่ม</p></div><button autoFocus type="button" className="button secondary" aria-label="ปิดพรีวิว Pipeline" onClick={onClose}><X size={18}/>ปิด</button></header>
   <div className="grid min-h-0 flex-1 gap-4 overflow-auto p-4 lg:grid-cols-2">
    <section className="min-w-0 lg:sticky lg:top-0 lg:self-start" aria-label="ภาพและกรอบ DET">
     <p className="mb-2 text-xs"><span className="font-semibold text-yellow-700">สีเหลือง: Global Field</span> · <span className="text-indigo-700">สีม่วง: DET</span> · คลิกบล็อก Field เพื่อไฮไลต์</p>
     <DocumentViewer onClearSelection={()=>{setActiveField(null);setSelected(null);}} reviewMode globalFieldColor="#eab308" globalFields={fields.filter(f=>!fieldId||f.id===fieldId)} selectedGlobalFieldId={activeField} onSelectGlobalField={id=>{setActiveField(id);setSelected(null);}} imageUrl={assetUrl(saved.document.image_url)} width={saved.document.width} height={saved.document.height} roi={null} onRoiChange={()=>{}} boxes={boxes} highlightedBoxIds={highlightedBoxIds} selectedBoxId={selected} onSelectBox={id=>{setSelected(id);const owner=predictions.find(f=>resultPreviewBoxes([f],run.pipeline_id).some(b=>b.id===id));if(owner?.global_field_id)setActiveField(owner.global_field_id);}} regionMode={false} onRegionModeChange={()=>{}} allowRoi={false} showRoiDelete={false}/>
     <p className="mt-2 text-sm text-slate-500" data-testid="det-box-count">{boxes.length?`กรอบ DET ${boxes.length} กรอบ`:"ไม่มีพิกัด DET ที่บันทึกไว้สำหรับผลนี้"}</p>
    </section>
    <section className="min-w-0 space-y-4" aria-label="ผล OCR ที่บันทึกไว้">
     {!fieldId&&<article className="panel panel-body"><h3>Whole Field · Extracted Text</h3><p className="mt-3 whitespace-pre-wrap break-words">{run.final_text||"(ไม่พบข้อความ)"}</p><p className="mt-3 text-sm">Confidence {pct(run.confidence)} · CER {pct(documentGT===(saved.ground_truth_raw??"")?run.document_evaluation?.cer:null)} · WER {pct(documentGT===(saved.ground_truth_raw??"")?run.document_evaluation?.wer:null)}</p></article>}
     {predictions.map(field=>{
      const current=fields.find(f=>f.id===field.global_field_id),original=saved.global_fields?.find(f=>f.id===field.global_field_id);
      const evaluation=field.status==="error"||current?.ground_truth_raw!==original?.ground_truth_raw?null:field.evaluation;
      const det=resultPreviewBoxes([field],run.pipeline_id);
      return <article key={field.id} className={`panel panel-body space-y-3 ${activeField===field.global_field_id?"ring-2 ring-yellow-400 bg-yellow-50":""}`} data-testid="expanded-field-result" onClick={()=>{setActiveField(field.global_field_id??null);setSelected(null);}}><h3><button type="button" className="w-full text-left" aria-pressed={activeField===field.global_field_id} onClick={()=>{setActiveField(field.global_field_id??null);setSelected(null);}}>Field {String(field.field_index).padStart(2,"0")}</button></h3>{field.status==="error"&&<p className="text-amber-800">OCR ของ Field นี้ไม่สำเร็จ</p>}<h4 className="text-xs text-slate-500">Extracted Text</h4><p className="whitespace-pre-wrap break-words">{field.ocr_text||"(ไม่พบข้อความ)"}</p><dl className="grid grid-cols-2 gap-3 rounded-lg bg-slate-50 p-3 text-sm">{[["Confidence",pct(field.confidence)],["CER",pct(evaluation?.cer)],["WER",pct(evaluation?.wer)],["Exact Match",evaluation?(evaluation.exact_match?"✓ Yes":"✕ No"):"—"]].map(([label,value])=><div key={label}><dt className="text-slate-500">{label}</dt><dd>{value}</dd></div>)}</dl>{!evaluation&&<p className="text-xs text-slate-500">ยังไม่ประเมิน</p>}
       <ErrorAnalysis evaluation={evaluation} groundTruth={current?.ground_truth_raw??""}/>
       {!!det.length&&<section className="space-y-2"><h4 className="text-sm font-semibold">กรอบ DET ของข้อความ ({det.length})</h4><p className="text-xs text-slate-500">กดข้อความด้านล่างเพื่อไฮไลต์กรอบ DET บนภาพ</p>{det.map((box,i)=><button key={box.id} type="button" aria-label={`ดูกรอบ DET ${i+1}: ${box.text||"ไม่มีข้อความ"}`} aria-pressed={selected===box.id} className={`flex w-full items-start gap-3 rounded-lg border p-3 text-left text-sm transition-colors hover:border-indigo-400 hover:bg-indigo-50 ${selected===box.id?"border-indigo-500 bg-indigo-50 ring-1 ring-indigo-300":"border-indigo-200 bg-white"}`} onClick={event=>{event.stopPropagation();setActiveField(field.global_field_id??null);setSelected(box.id);}}><ScanLine size={20} className="mt-0.5 shrink-0 text-indigo-600"/><span className="min-w-0"><span className="block text-xs font-semibold text-indigo-700">ดูกรอบ DET {i+1} บนภาพ</span><span className="mt-1 block whitespace-pre-wrap break-words">{box.text||"(ไม่มีข้อความ)"}</span></span></button>)}</section>}
      </article>;
     })}
     {!predictions.length&&<p>ไม่มีผลลัพธ์ราย Field ที่บันทึกไว้</p>}
    </section>
   </div>
  </div>
 </dialog>;
}
