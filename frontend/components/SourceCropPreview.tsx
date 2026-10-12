"use client";
import {useEffect,useRef,useState} from "react";
import {assetUrl,cropUrl} from "@/lib/api";
import type {ROI} from "@/types";
import InsightDialog from "./InsightDialog";
export default function SourceCropPreview({documentId,page,roi,onClose}:{documentId:string;page:number|null;roi:ROI;onClose:()=>void}){
 const viewport=useRef<HTMLDivElement>(null),drag=useRef<{x:number;y:number;left:number;top:number}|null>(null);
 const [full,setFull]=useState(false),[size,setSize]=useState({width:1,height:1}),[zoom,setZoom]=useState(1),[failed,setFailed]=useState(false);
 useEffect(()=>{
  const el=viewport.current;
  const wheel=(event:WheelEvent)=>{
   if(event.ctrlKey||event.metaKey){
    event.preventDefault();
    setZoom(z=>Math.max(.05,Math.min(8,z*Math.exp(-event.deltaY*.005))));
   }
  };
  el?.addEventListener("wheel",wheel,{passive:false});
  return()=>el?.removeEventListener("wheel",wheel);
 },[]);
 const url=full?assetUrl(`/api/documents/${documentId}${page?`/pages/${page}`:""}/image`):cropUrl(documentId,roi,page);
 function fit(width=size.width,height=size.height){const el=viewport.current;if(el){setZoom(Math.min(1,(el.clientWidth-20)/width,(el.clientHeight-20)/height));el.scrollTo(0,0);}}
 return <InsightDialog title={full?"เอกสารต้นฉบับพร้อมกรอบ Field":"ภาพต้นฉบับตาม ROI ของ Field"} onClose={onClose}>
 <p className="mb-3 text-sm text-slate-600">หน้า {page??1} · แสดงบริเวณ Field/หน้า ไม่ใช่ตำแหน่งอักขระที่แม่นยำ</p>
 <div className="mb-3 flex flex-wrap gap-2"><button className="button secondary" onClick={()=>setZoom(z=>Math.min(8,z*1.25))}>ขยาย</button><button className="button secondary" onClick={()=>setZoom(z=>Math.max(.05,z/1.25))}>ย่อ</button><button className="button secondary" onClick={()=>fit()}>พอดีหน้าต่าง</button><button className="button secondary" onClick={()=>{setFull(v=>!v);setFailed(false);}}>{full?"กลับไปภาพของ Field":"ดูเอกสารต้นฉบับ"}</button><output aria-label="ระดับการซูม">{Math.round(zoom*100)}%</output></div>
 {failed&&<p role="alert">ไม่พบภาพต้นฉบับหรือไม่สามารถโหลดได้ กรุณากู้ไฟล์หรืออัปโหลดใหม่</p>}
 <div ref={viewport} role="region" aria-label="เลื่อนภาพต้นฉบับ" tabIndex={0} className="relative h-[60dvh] min-h-64 overflow-auto rounded-lg bg-slate-100 outline-indigo-500" style={{touchAction:"pan-x pan-y"}}
 onPointerDown={e=>{if(e.pointerType!=="mouse")return;const el=viewport.current!;drag.current={x:e.clientX,y:e.clientY,left:el.scrollLeft,top:el.scrollTop};el.setPointerCapture(e.pointerId);}}
 onPointerMove={e=>{if(drag.current){const el=viewport.current!;el.scrollLeft=drag.current.left+drag.current.x-e.clientX;el.scrollTop=drag.current.top+drag.current.y-e.clientY;}}}
 onPointerUp={()=>{drag.current=null;}} onPointerCancel={()=>{drag.current=null;}}
>
 <div className="relative" style={{width:size.width*zoom,height:size.height*zoom}}>
 {/* Original pixels are served by the existing document endpoint, without Next image optimization. */}
 {/* eslint-disable-next-line @next/next/no-img-element */}
 <img key={url} src={url} alt={full?"เอกสารต้นฉบับ":"ภาพต้นฉบับของ Field"} draggable={false} onError={()=>setFailed(true)} onLoad={e=>{const {naturalWidth:width,naturalHeight:height}=e.currentTarget;setSize({width,height});fit(width,height);}} style={{width:size.width*zoom,height:size.height*zoom,maxWidth:"none"}}/>
 {full&&<div aria-label="Global Field region" className="pointer-events-none absolute border-2 border-amber-500 bg-amber-200/10" style={{left:roi.x1*zoom,top:roi.y1*zoom,width:(roi.x2-roi.x1)*zoom,height:(roi.y2-roi.y1)*zoom}}/>}
 </div></div><p className="mt-2 text-xs text-slate-500">ลากเพื่อเลื่อน · Ctrl/Cmd + wheel เพื่อซูม · ใช้ปุ่มลูกศรเลื่อนเมื่อโฟกัสภาพ</p>
 </InsightDialog>;
}
