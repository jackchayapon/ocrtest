"use client";
import {useState} from "react";
import type {ErrorInsights, InsightScope} from "@/types/evaluation-insights";
import SourceCropPreview from "./SourceCropPreview";

function ErrorExcerpt({text,highlight,missing,kind}:{text:string;highlight?:{start:number;length:number};missing:string|null;kind:string}) {
 if(!highlight)return <>{text}</>;
 // Backend positions count Unicode code points, not JavaScript UTF-16 units.
 const chars=Array.from(text),{start,length}=highlight;
 const visible=(value:string)=>value.replace(/ /g,"␣");
 return <>{chars.slice(0,start).join("")}<mark
  className={length?"rounded bg-red-200 px-0.5 text-red-950 underline decoration-red-600":"rounded border border-amber-500 bg-amber-100 px-1 text-amber-950"}
  title={kind==="insertion"?"ข้อความที่ OCR อ่านเกินจาก Ground Truth":length?"อักขระที่เกี่ยวข้องกับข้อผิดพลาด":"ตำแหน่งที่ OCR อ่านขาดหาย"}
 >{length?(kind==="insertion"?`[เกิน: ${visible(chars.slice(start,start+length).join(""))}]`:visible(chars.slice(start,start+length).join(""))):`[ขาด: ${visible(missing??"")}]`}</mark>{chars.slice(start+length).join("")}</>;
}

export default function FieldErrorDetails({data,run}:{data:ErrorInsights;run:ErrorInsights["pipelines"][number]}) {
 const [expanded,setExpanded]=useState<Record<string,boolean>>({});
 const groups=new Map<string,{index:number|null;roi:InsightScope["roi"];gt?:string;ocr?:string;details:InsightScope["details"]}>();
 for(const scope of run.scopes.filter(s=>s.state==="ready")) {
  for(const detail of scope.details) {
   const source=detail.source_field;
   const key=source?.id??scope.global_field_id??scope.field_id??"document";
   const group=groups.get(key)??{index:source?.field_index??scope.field_index,roi:source?.roi??scope.roi,gt:source?.ground_truth??(source?undefined:scope.display_ground_truth),ocr:source?.ocr_text??(source?undefined:scope.display_ocr_text),details:[]};
   group.details.push(detail);groups.set(key,group);
  }
 }
 return <div className="space-y-3">{Array.from(groups).sort(([,a],[,b])=>(a.index??Infinity)-(b.index??Infinity)).map(([key,group])=><article key={key} className="rounded-lg border border-red-100 bg-red-50 p-4 break-words">
  <h4 className="font-semibold">{run.pipeline_name} · {group.index==null?"ทั้งเอกสาร (ไม่สามารถระบุ Field ได้)":`Field ${String(group.index).padStart(2,"0")}`}</h4>
  <p data-testid="field-error-ground-truth" className="mt-3 whitespace-pre-wrap rounded bg-sky-50 p-3"><span className="block font-medium text-sky-900">ข้อความจริง (Ground Truth): </span>{group.gt??Array.from(new Set(group.details.map(e=>e.ground_truth_excerpt))).join("\n")}</p>
  <p data-testid="field-error-raw-ocr" className="mt-2 whitespace-pre-wrap rounded bg-slate-50 p-3"><span className="block font-medium">ข้อความที่ OCR อ่านได้: </span>{group.ocr??Array.from(new Set(group.details.map(e=>e.ocr_excerpt))).join("\n")}</p>
  <div className="mt-3 space-y-3">{group.details.map((e,i)=><div key={i} className="space-y-2 rounded-lg border border-red-100 bg-white p-3">
   <p className="font-medium">{e.explanation??({substitution:"อ่านผิด",deletion:"อ่านขาดหาย",insertion:"อ่านเกิน"})[e.error_type as "substitution"|"deletion"|"insertion"]}</p>
   {e.line_number!=null&&<p className="text-slate-500">บรรทัด {e.line_number}</p>}
   <p className="whitespace-pre-wrap rounded bg-slate-50 p-2"><span className="block font-medium">ข้อความที่ OCR อ่านได้: </span><ErrorExcerpt text={e.ocr_excerpt} highlight={e.ocr_highlight} missing={e.ground_truth_unit} kind={e.error_type}/></p>
  </div>)}</div>
  <button className="button secondary mt-2" aria-expanded={!!expanded[key]} onClick={()=>setExpanded(v=>({...v,[key]:!v[key]}))}>
   {expanded[key]?"▾ ซ่อนภาพต้นฉบับ":group.index==null?"▸ ดูภาพต้นฉบับ (ทั้งเอกสาร)":"▸ ดูภาพต้นฉบับ (Field Crop)"}
  </button>
  {expanded[key]&&<SourceCropPreview documentId={data.document_id} page={data.page_number} roi={group.roi}/>}
 </article>)}
 {run.scopes.some(s=>s.details_truncated)&&<p>แสดงตัวอย่างสูงสุด 50 รายการต่อส่วน · ดูรายการทั้งหมดในรายงานผลการประเมิน</p>}
 </div>;
}
