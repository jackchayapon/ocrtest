"use client";
import {useState} from "react";
import type {ErrorInsights, InsightScope} from "@/types/evaluation-insights";
import SourceCropPreview from "./SourceCropPreview";

function ErrorExcerpt({text,highlight,missing}:{text:string;highlight?:{start:number;length:number};missing:string|null}) {
 if(!highlight)return <>{text}</>;
 // Backend positions count Unicode code points, not JavaScript UTF-16 units.
 const chars=Array.from(text),{start,length}=highlight;
 const visible=(value:string)=>value.replace(/ /g,"␣");
 return <>{chars.slice(0,start).join("")}<mark
  className={length?"rounded bg-red-200 px-0.5 text-red-950 underline decoration-red-600":"rounded border border-amber-500 bg-amber-100 px-1 text-amber-950"}
  title={length?"อักขระที่เกี่ยวข้องกับข้อผิดพลาด":"ตำแหน่งที่ OCR อ่านขาดหาย"}
 >{length?visible(chars.slice(start,start+length).join("")):`[ขาด: ${visible(missing??"")}]`}</mark>{chars.slice(start+length).join("")}</>;
}

export default function FieldErrorDetails({data,run}:{data:ErrorInsights;run:ErrorInsights["pipelines"][number]}) {
 const [expanded,setExpanded]=useState<Record<string,boolean>>({});
 const groups=new Map<string,{index:number|null;roi:InsightScope["roi"];details:InsightScope["details"]}>();
 for(const scope of run.scopes.filter(s=>s.state==="ready")) {
  for(const detail of scope.details) {
   const source=detail.source_field;
   const key=source?.id??scope.global_field_id??scope.field_id??"document";
   const group=groups.get(key)??{index:source?.field_index??scope.field_index,roi:source?.roi??scope.roi,details:[]};
   group.details.push(detail);groups.set(key,group);
  }
 }
 return <div className="space-y-3">{Array.from(groups,([key,group])=><article key={key} className="rounded-lg border border-red-100 bg-red-50 p-4 break-words">
  <h4 className="font-semibold">{run.pipeline_name} · {group.index==null?"ทั้งเอกสาร (ไม่สามารถระบุ Field ได้)":`Field ${String(group.index).padStart(2,"0")}`}</h4>
  <div className="divide-y divide-red-100">{group.details.map((e,i)=><div key={i} className="space-y-1 py-3">
   <p className="font-medium">{e.explanation??({substitution:"อ่านผิด",deletion:"อ่านขาดหาย",insertion:"อ่านเกิน"})[e.error_type as "substitution"|"deletion"|"insertion"]}</p>
   {e.line_number!=null&&<p className="text-slate-500">บรรทัด {e.line_number}</p>}
   <p className="whitespace-pre-wrap">ข้อความจริง (Ground Truth): {e.ground_truth_highlight?.length===0?e.ground_truth_excerpt:<ErrorExcerpt text={e.ground_truth_excerpt} highlight={e.ground_truth_highlight} missing={null}/>}</p>
   <p className="whitespace-pre-wrap">ข้อความที่ OCR อ่านได้: <ErrorExcerpt text={e.ocr_excerpt} highlight={e.ocr_highlight} missing={e.ground_truth_unit}/></p>
  </div>)}</div>
  <button className="button secondary mt-2" aria-expanded={!!expanded[key]} onClick={()=>setExpanded(v=>({...v,[key]:!v[key]}))}>
   {expanded[key]?"▾ ซ่อนภาพต้นฉบับ":group.index==null?"▸ ดูภาพต้นฉบับ (ทั้งเอกสาร)":"▸ ดูภาพต้นฉบับ (Field Crop)"}
  </button>
  {expanded[key]&&<SourceCropPreview documentId={data.document_id} page={data.page_number} roi={group.roi}/>}
 </article>)}
 {run.scopes.some(s=>s.details_truncated)&&<p>แสดงตัวอย่างสูงสุด 50 รายการต่อส่วน · ดูรายการทั้งหมดในรายงานผลการประเมิน</p>}
 </div>;
}
