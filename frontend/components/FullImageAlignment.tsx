"use client";
import {useEffect,useRef,useState} from 'react';
import {MousePointer2,ZoomIn,ZoomOut,Maximize,RotateCcw,ScanLine} from 'lucide-react';
import type {SharedDocumentView,DocumentViewControls} from './DocumentViewer';
import dynamic from 'next/dynamic';
import type {PipelineRun,TestCase} from '@/types';
import type {SpatialReference,SpatialOverride,SpatialResult,AlignmentCheck} from '@/types/spatial-comparison';
import {assetUrl,compareSpatial,getFullImageReferences,getAlignmentReview} from '@/lib/api';
import {resultPreviewBoxes} from '@/lib/result-preview';
import {pipelineLabel} from '@/lib/i18n/th';
const DocumentViewer=dynamic(()=>import('./DocumentViewer'),{ssr:false});
type Props={saved:TestCase;runs:PipelineRun[];text:string;busy:boolean;initialRunId?:string;onConfirm:(runId:string,refs:SpatialReference[],overrides:SpatialOverride[],textOnly?:boolean)=>Promise<void>;onClear:(runId:string)=>Promise<void>;onDirty:(dirty:boolean)=>void};
const reasons:Record<string,string>={matched:'ตำแหน่งตรง',mismatch:'ตำแหน่งไม่ตรง ต้องแก้',confirm_gaps:'ต้องยืนยันกรอบขาด/เกิน',gaps_confirmed:'ยืนยันกรอบขาด/เกินแล้ว',geometry_unavailable:'ตรวจตำแหน่งไม่ได้ ต้องยืนยันข้อความ',text_only_confirmed:'ยืนยันเทียบข้อความ (ไม่มีพิกัดครบ)',stale_alignment:'GT เปลี่ยน ต้องยืนยันใหม่'};

export default function FullImageAlignment(props:Props){
 const runs=props.runs.filter(r=>r.status==='success');
 const [runId,setRunId]=useState(props.initialRunId??runs[0]?.id??'');
 const [checks,setChecks]=useState<AlignmentCheck[]>([]),[reviewError,setReviewError]=useState('');
 const [dirty,setDirty]=useState(false),[seed,setSeed]=useState<SpatialReference[]|null>(null),[error,setError]=useState('');
 const run=runs.find(r=>r.id===runId)??runs[0];
 useEffect(()=>{let cancelled=false;getAlignmentReview(props.saved.id).then(review=>{if(!cancelled){setChecks(review.pipelines);setReviewError('');}}).catch(e=>{if(!cancelled)setReviewError(e instanceof Error?e.message:'ตรวจ Pipeline ไม่สำเร็จ');});return()=>{cancelled=true;};},[props.saved]);
 function status(id:string){const check=checks.find(c=>c.run_id===id);const edited=dirty&&id===run?.id||props.text!==(props.saved.ground_truth_raw??'');return {ready:!edited&&!!check?.ready,label:edited?'มีการแก้ไข ต้องยืนยัน':check?reasons[check.reason]??check.reason:'กำลังตรวจ'};}
 useEffect(()=>{let cancelled=false;getFullImageReferences(props.saved.id).then(data=>{
  if(!cancelled)setSeed(props.text.replace(/\r\n?/g,'\n').split('\n').map((text,i)=>({id:`gt-${i}`,text,roi:data.references[i]?.roi??null})));
 }).catch(e=>{if(!cancelled)setError(e instanceof Error?e.message:'โหลดกรอบ GT ไม่สำเร็จ');});return()=>{cancelled=true;};},[props.saved.id,props.text]);
 return <section className="space-y-4" aria-label="จัดตำแหน่ง GT เทียบ DET">
  <p>ระบบเทียบกรอบ GT กับ DET ให้อัตโนมัติ กรอบสีแดงคือคู่ที่ตำแหน่งหรือลำดับไม่ตรงกัน</p>
  <p className="text-sm text-slate-600">GT เป็นตัวอ้างอิงคงที่ เลือกสองกรอบฝั่ง Pipeline เพื่อสลับ Field ID โดยไม่เปลี่ยนพิกัดกรอบ</p>
  <label>Pipeline ที่ตรวจ <select className="input" aria-label="Pipeline จัดตำแหน่ง" disabled={props.busy||dirty} value={run?.id??''} onChange={e=>setRunId(e.target.value)}>{runs.map(r=><option key={r.id} value={r.id}>{status(r.id).ready?'✅':'🔴'} {pipelineLabel(r.pipeline_id,r.pipeline_name)} · {status(r.id).label}</option>)}</select></label>
  <div className="grid gap-3 md:grid-cols-2" aria-label="สถานะตรวจ Pipeline">{[true,false].map(ready=><section key={String(ready)} className={`rounded-lg border p-3 ${ready?'border-green-300 bg-green-50':'border-red-300 bg-red-50'}`}><h3 className={`mb-3 font-semibold ${ready?'text-green-800':'text-red-800'}`}>{ready?'✓ Pipeline ที่ผ่านแล้ว':'✕ Pipeline ที่ต้องตรวจ / แก้ไข'}</h3><div className="flex flex-wrap gap-2">{runs.filter(r=>status(r.id).ready===ready).map(r=>{const s=status(r.id);return <button type="button" key={r.id} disabled={props.busy||dirty} aria-pressed={run?.id===r.id} data-testid={`alignment-status-${r.id}`} className={`rounded border bg-white px-3 py-2 text-sm ${s.ready?'border-green-500 text-green-800':'border-red-400 text-red-800'} ${run?.id===r.id?'ring-2 ring-indigo-400':''}`} onClick={()=>setRunId(r.id)}>{s.ready?'✓':'✕'} {pipelineLabel(r.pipeline_id,r.pipeline_name)} · {s.label}</button>;})}{!runs.some(r=>status(r.id).ready===ready)&&<p className="text-sm text-slate-500">ไม่มีรายการ</p>}</div></section>)}</div>
  {reviewError&&<p role="alert">{reviewError}</p>}
  {dirty&&<p className="text-amber-800">สลับ Field ID แล้ว กรุณายืนยันหรือยกเลิกก่อนเปลี่ยน Pipeline หรือปิด Preview</p>}
  {error?<p role="alert">{error}</p>:!seed?<p role="status">กำลังโหลดกรอบ GT และตรวจตำแหน่ง…</p>:run?<Editor key={run.id} {...props} seed={seed} run={run} onDirty={value=>{setDirty(value);props.onDirty(value);}}/>:<p>ยังไม่มี Pipeline ที่รันสำเร็จ</p>}
 </section>;
}

function Editor({saved,run,text,seed,busy,onConfirm,onClear,onDirty}:Props&{run:PipelineRun;seed:SpatialReference[]}){
 const stored=saved.full_image_alignment?.[run.id];
 const refs=seed;
 const boxes=resultPreviewBoxes(run.fields??[],run.pipeline_id);
 const needsPadding=boxes.length>0&&boxes.length<refs.length&&refs.every(r=>r.roi);
 const validStored=stored?.fixed_gt&&(!needsPadding||stored.padding_version===1)&&stored.source_ground_truth===text.replace(/\r\n?/g,'\n')&&stored.references.length===seed.length&&stored.references.every((r,i)=>r.id===seed[i].id&&r.text===seed[i].text&&(r.roi===null?seed[i].roi===null:!!seed[i].roi&&(['x1','y1','x2','y2'] as const).every(key=>r.roi![key]===seed[i].roi![key])));
 const defaults=()=>needsPadding?[]:boxes.map((b,i)=>({box_id:b.id,reference_id:refs[i]?.id??null}));
 const initial=()=>validStored?stored.overrides:defaults();
 const [overrides,setOverrides]=useState<SpatialOverride[]>(initial);
 const [active,setActive]=useState<string|null>(null),[other,setOther]=useState('');
 const [selectedGT,setSelectedGT]=useState<string|null>(null);
 const [sharedView,setSharedView]=useState<SharedDocumentView|null>(null),[showLabels,setShowLabels]=useState(true);
 const viewControls=useRef<DocumentViewControls|null>(null);
 const [working,setWorking]=useState(true),[error,setError]=useState('');
 const [result,setResult]=useState<SpatialResult|null>(null),[dirty,setDirty]=useState(false);
 const disabled=busy||working;
 const textOnly=!boxes.length||refs.some(r=>!r.roi);
 const assignments=overrides.length?overrides:(result?.matches.map(m=>({box_id:m.id,reference_id:m.reference_id}))??[]);
 const placeholders=boxes.length?refs.filter(r=>result?.rows.some(row=>row.id===r.id&&row.status==='missing')):[];
 useEffect(()=>{let cancelled=false;compareSpatial(saved.id,{run_id:run.id,references:refs,overrides,confirmed_gt:false}).then(value=>{
  if(!cancelled){setResult(value);setError('');}
 }).catch(e=>{if(!cancelled)setError(e instanceof Error?e.message:'ตรวจตำแหน่งไม่สำเร็จ');}).finally(()=>{if(!cancelled)setWorking(false);});return()=>{cancelled=true;};},[saved.id,run.id,refs,overrides]);
 function swap(){
  const a=assignments.find(o=>o.box_id===active),b=assignments.find(o=>o.box_id===other);
  if(!a||!b||a.box_id===b.box_id)return;
  // Only the pipeline box -> GT identity association changes. GT and both geometries are immutable.
  setOverrides(assignments.map(o=>o.box_id===a.box_id?{...o,reference_id:b.reference_id}:o.box_id===b.box_id?{...o,reference_id:a.reference_id}:o));
  setOther('');setResult(null);setWorking(true);setDirty(true);onDirty(true);
 }
 const mismatches=new Set(refs.some(r=>r.roi)?result?.matches.filter(m=>!m.reference_id||!m.candidates.some(c=>c.reference_id===m.reference_id)).map(m=>m.id):[]);
 const wrongPair=result?.matches.some(m=>m.reference_id&&!m.candidates.some(c=>c.reference_id===m.reference_id));
 const fieldNumber=(id:string)=>{const ref=assignments.find(o=>o.box_id===id)?.reference_id;const index=refs.findIndex(r=>r.id===ref);return index<0?null:index+1;};
 const boxLabel=(id:string,i:number)=>`${fieldNumber(id)==null?'ไม่จับคู่':`Field ${String(fieldNumber(id)).padStart(2,'0')}`} · กรอบ DET ${i+1}`;
 const badRefs=new Set(result?.rows.filter(r=>r.status==='missing'||r.status==='ambiguous'||result.matches.some(m=>m.reference_id===r.id&&mismatches.has(m.id))).map(r=>r.id));
 const viewer={imageUrl:assetUrl(saved.document.image_url),width:saved.document.width,height:saved.document.height,roi:null,onRoiChange:()=>{},boxes:[],selectedBoxId:null,onSelectBox:()=>{},allowRoi:false,showRoiDelete:false,regionMode:false,onRegionModeChange:()=>{},reviewMode:true,hideToolbar:true,combinedNavigation:true,sharedView,onSharedViewChange:setSharedView,fieldLabelsVisible:showLabels};
 return <>
  {working&&<p role="status">กำลังเทียบตำแหน่ง…</p>}
  {!refs.some(r=>r.roi)&&<p role="status">เคสนี้ไม่มีพิกัด DET ของ GT ที่บันทึกไว้ จึงยังตรวจตำแหน่ง GT ไม่ได้ โดยคง Field และข้อความเดิมไว้</p>}
  {!boxes.length&&<p role="status">Pipeline นี้ไม่มีพิกัด DET จะคงการเทียบข้อความเดิม</p>}
  {textOnly&&<p className="rounded border border-amber-400 bg-amber-50 p-3">พิกัด GT หรือ DET ไม่ครบ จึงยังยืนยันว่าตำแหน่งตรงกันไม่ได้ โปรดตรวจข้อความและยืนยันการเทียบข้อความเดิมก่อนคำนวณ</p>}
  {!!placeholders.length&&<p role="status" className="rounded border border-yellow-400 bg-yellow-50 p-3">GT {refs.length} Fields · Pipeline พบจริง {boxes.length} กรอบ + Field ว่าง {placeholders.length} รายการ กรอบสีเหลืองเพิ่มเพื่อให้เทียบตรงกับ GT เท่านั้น ไม่ใช่ผล DET ใช้ข้อความว่างในการคำนวณ และล็อกไม่ให้สลับ</p>}
  <div role="toolbar" aria-label="ควบคุมภาพ GT และ Pipeline ร่วมกัน" className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-white p-3">
   <div className="flex flex-wrap items-center gap-2">
    <button type="button" className="button secondary bg-indigo-50" aria-label="เลือกกรอบและเลื่อนภาพ" aria-pressed="true" title="คลิกกรอบเพื่อเลือก Field หรือลากพื้นที่ว่างเพื่อเลื่อนภาพ" onClick={()=>{setActive(null);setSelectedGT(null);setOther('');}}><MousePointer2 size={18}/>เลือกกรอบ / เลื่อนภาพ</button>
    <button type="button" className="button secondary" aria-label="ซ่อนชื่อ Field ทั้งสองภาพ" aria-pressed={!showLabels} onClick={()=>setShowLabels(value=>!value)}><ScanLine size={18}/>{showLabels?'ซ่อนชื่อ Field':'แสดงชื่อ Field'}</button>
   </div>
   <div className="flex items-center gap-2">
    <button type="button" className="button secondary" aria-label="ย่อทั้งสองภาพ" onClick={()=>viewControls.current?.zoomOut()}><ZoomOut size={18}/></button>
    <button type="button" className="button secondary min-w-16" aria-label="ซูมทั้งสองภาพ 100%" onClick={()=>viewControls.current?.actualSize()}>{sharedView?`${Math.round(sharedView.scale*100)}%`:'—'}</button>
    <button type="button" className="button secondary" aria-label="ขยายทั้งสองภาพ" onClick={()=>viewControls.current?.zoomIn()}><ZoomIn size={18}/></button>
    <button type="button" className="button secondary" aria-label="พอดีหน้าจอทั้งสองภาพ" onClick={()=>viewControls.current?.fit()}><Maximize size={18}/></button>
    <button type="button" className="button secondary" aria-label="รีเซ็ตทั้งสองภาพ" onClick={()=>{viewControls.current?.fit();setActive(null);setSelectedGT(null);setOther('');}}><RotateCcw size={18}/></button>
   </div>
  </div>
  <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(280px,0.65fr)]">
   <section className="min-w-0" aria-label="กรอบ GT คงที่"><h3>Ground Truth · ตัวอ้างอิงคงที่</h3><DocumentViewer {...viewer}
    controlsRef={viewControls} selectedGlobalFieldId={selectedGT} onSelectGlobalField={setSelectedGT} onClearSelection={()=>setSelectedGT(null)}
    globalFields={refs.flatMap((r,i)=>r.roi?[{id:r.id,roi:r.roi,field_index:i+1}]:[])} globalFieldColor="#ca8a04" mismatchFieldIds={[...badRefs]}
    /></section>
   <section className="min-w-0" aria-label="กรอบ Pipeline คงที่"><h3>{pipelineLabel(run.pipeline_id,run.pipeline_name)}</h3><DocumentViewer {...viewer}
    globalFields={[...boxes.map((b,i)=>({id:b.id,field_index:fieldNumber(b.id)??i+1,roi:{x1:b.bbox[0],y1:b.bbox[1],x2:b.bbox[2],y2:b.bbox[3]}})),...placeholders.flatMap(r=>r.roi?[{id:`placeholder:${r.id}`,field_index:refs.indexOf(r)+1,roi:r.roi,placeholder:true}]:[])]}
    selectedGlobalFieldId={active} onClearSelection={()=>{setActive(null);setOther('');}} onSelectGlobalField={id=>{if(!disabled&&boxes.some(b=>b.id===id)){setActive(id);setOther('');}}} mismatchFieldIds={[...mismatches]} globalFieldColor="#6366f1"/></section>
  <fieldset disabled={disabled} className="min-w-0 space-y-3 rounded-lg border bg-slate-50 p-4">
   <legend className="px-2 font-semibold">สลับ Field ID · {pipelineLabel(run.pipeline_id,run.pipeline_name)}</legend>
   <div className="flex flex-wrap items-center gap-3">
    <label>Pipeline Field แรก <select className="input" aria-label="Pipeline Field แรก" value={active??''} onChange={e=>{setActive(e.target.value);setOther('');}}><option value="">เลือกกรอบ Pipeline</option>{boxes.map((b,i)=><option key={b.id} value={b.id}>{boxLabel(b.id,i)}</option>)}</select></label>
    <label>สลับกับ Pipeline Field <select className="input" aria-label="สลับกับ Pipeline Field" value={other} onChange={e=>setOther(e.target.value)}><option value="">เลือกกรอบ Pipeline</option>{boxes.map((b,i)=><option key={b.id} disabled={b.id===active} value={b.id}>{boxLabel(b.id,i)}</option>)}</select></label>
    <button className="button secondary" disabled={disabled||!active||!other} onClick={swap}>สลับ Pipeline Field ID</button>
   </div>
   {placeholders.map(r=><div key={r.id} data-testid={`placeholder-${r.id}`} className="rounded border border-yellow-400 bg-yellow-50 p-3"><strong>Field {String(refs.indexOf(r)+1).padStart(2,'0')} · Field ว่าง · ล็อก</strong> <span className="rounded-full bg-yellow-200 px-2 py-1 text-xs">เติมกรอบว่าง</span><p>เพิ่มเพื่อเทียบตรงกับ GT เท่านั้น · ข้อความ OCR = ว่าง · สลับไม่ได้</p></div>)}
   <div className="max-h-[50vh] overflow-auto space-y-2">{boxes.map((b,i)=>{const changed=assignments.find(o=>o.box_id===b.id)?.reference_id!==(refs[i]?.id??null);return <div key={b.id} className={`rounded border bg-white p-2 ${mismatches.has(b.id)?'border-red-500':'border-slate-200'}`}><button className="underline" onClick={()=>{setActive(b.id);setOther('');}}>{boxLabel(b.id,i)}</button> <span className={`inline-block rounded-full px-2 py-1 text-xs ${changed?'bg-indigo-100 text-indigo-800':'bg-slate-100 text-slate-600'}`}>{changed?'สลับแล้ว':'คงเดิม'}</span><p className="mt-2 break-words">{b.text||'(ไม่มีข้อความ)'}</p></div>;})}{refs.filter(r=>!r.roi).map(r=><p key={r.id}>GT Field {refs.indexOf(r)+1} · ไม่มีกรอบ — คง Field ไว้</p>)}</div>
   {result&&<p role="status">กรอบขาด {result.missing} · กรอบเกิน {result.extra} · กรอบตำแหน่งไม่ตรง {mismatches.size}</p>}
   <div className="flex flex-wrap gap-2"><button className="button primary" disabled={disabled||!result||(!textOnly&&(!!result.ambiguous||!!wrongPair))} onClick={async()=>{setWorking(true);try{await onConfirm(run.id,refs,assignments,textOnly);setDirty(false);onDirty(false);}catch(e){setError(e instanceof Error?e.message:'ยืนยันไม่สำเร็จ');}finally{setWorking(false);}}}>{textOnly?'ยืนยันเทียบข้อความเดิม (พิกัดไม่ครบ)':'ยืนยัน Field ID สำหรับ Pipeline นี้'}</button>
    {dirty&&<button className="button secondary" onClick={()=>{setOverrides(initial());setResult(null);setWorking(true);setDirty(false);onDirty(false);}}>ยกเลิกการสลับ</button>}
    {stored&&<button className="button secondary" onClick={async()=>{setWorking(true);try{await onClear(run.id);setOverrides(defaults());setResult(null);setDirty(false);onDirty(false);}catch(e){setError(String(e));setWorking(false);}}}>ล้างการยืนยัน</button>}
   </div>
  </fieldset>
  </div>
  {stored&&!dirty&&<p role="status">{validStored?'บันทึก Field ID แล้ว — กดยืนยันคำนวณ GT ตามปกติ':'ต้องยืนยัน Pipeline Field ID ใหม่กับ GT คงที่'}</p>}
  {error&&<p role="alert" className="error-banner">{error}</p>}
 </>;
}
