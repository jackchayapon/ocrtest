import type {EvaluationMode,PipelineRun,ROI} from '@/types';
import {textLines} from '@/lib/full-image-lines';
import {useEffect,useRef,useState,type ReactNode} from 'react';

type Props={text:string;runs:PipelineRun[];busy:boolean;mode:EvaluationMode;onMode:(mode:EvaluationMode)=>void;onChange:(text:string)=>void;onSave:(calculate:boolean)=>void;inspection?:ReactNode;selectedIndex?:number;onSelectField?:(index:number)=>void;referenceRois?:(ROI|null)[]};

export default function FullImageLineFields({text,runs,busy,mode,onMode,onChange,onSave,inspection,selectedIndex,onSelectField,referenceRois}:Props){
 const [localActiveIndex,setActiveIndex]=useState(0);
 const activeIndex=selectedIndex??localActiveIndex;
 const fieldsContainer=useRef<HTMLDivElement>(null);
 const inputs=useRef(new Map<number,HTMLTextAreaElement>());
 const whole=mode==='whole_document';
 const lines=textLines(text);
 const lineCount=Math.max(lines.length,...runs.map(run=>textLines(run.final_text??'').length));
 const fieldName=(index:number)=>`Field ${String(index+1).padStart(2,'0')}`;
 const card='block rounded-xl border bg-slate-50 p-4 space-y-3 focus-within:border-sky-600 focus-within:ring-2 focus-within:ring-sky-600/25';
 const input='textarea w-full rounded-lg border border-slate-300 bg-white p-3 focus:border-sky-600 focus:outline-none focus:ring-2 focus:ring-sky-600/30';
 const predictions=runs.map(run=>textLines(run.final_text??''));
 function scrollField(index:number){const container=fieldsContainer.current,node=inputs.current.get(index)?.parentElement;if(!container||!node)return;const top=node.getBoundingClientRect().top-container.getBoundingClientRect().top+container.scrollTop;container.scrollTo({top:Math.max(0,top-4),behavior:'instant'});}
 useEffect(()=>{if(selectedIndex!==undefined&&selectedIndex>=0&&!whole)scrollField(selectedIndex);},[selectedIndex,whole]);
 function update(index:number,value:string){
  if(whole){onChange(value);return;}
  const next=[...lines];
  while(next.length<=index)next.push('');
  next[index]=value;
  onChange(next.join('\n'));
 }
 return <section className="panel panel-body space-y-4" data-testid="full-image-line-fields">
  {inspection}
  <div className="flex gap-2" aria-label="Evaluation mode">{(['whole_document','per_field'] as const).map(value=><button key={value} className={`button ${mode===value?'primary':'secondary'}`} disabled={busy} aria-pressed={mode===value} onClick={()=>onMode(value)}>{value==='whole_document'?'Whole Field':'Sub-fields'}</button>)}</div>
  <p className="text-sm text-slate-600">Whole Field แสดงข้อความทั้งหน้า · Sub-fields แยกจากข้อความ Whole Field ตามการขึ้นบรรทัดใหม่ โดยจับคู่ GT และ OCR ตามลำดับบรรทัด</p>
  {!whole&&predictions.some(prediction=>prediction.length!==lines.length)&&<p role="status" className="notice-banner">จำนวนบรรทัด GT และ OCR ไม่เท่ากัน ช่องที่ไม่มีบรรทัดคู่กันจะแสดงว่าง กรุณาตรวจลำดับก่อนยืนยัน</p>}
   {whole?<label className={`${card} border-slate-300`} data-testid="whole-gt-card">Ground Truth ทั้งเอกสาร<textarea className={input} rows={10} aria-label="Ground Truth ทั้งเอกสาร" disabled={busy} value={text} onChange={e=>onChange(e.target.value)}/></label>:<div ref={fieldsContainer} role="region" aria-label="ช่องกรอก Ground Truth ตาม Field" className="max-h-[65vh] [overflow-anchor:none] space-y-3 overflow-y-auto overscroll-contain p-1">
    {Array.from({length:lineCount},(_,index)=><label key={index} className={`${card} ${index===activeIndex?'ring-2 ring-violet-500':''} ${lines[index]?.trim()?'border-slate-300':'border-red-500'}`} data-testid="field-gt-input">
     <span className="flex items-start justify-between gap-2"><span>{fieldName(index)}</span>{!lines[index]?.trim()&&<span className="text-xs text-red-700">ยังไม่มี GT</span>}</span>
     <span className="block text-xs text-slate-500">บรรทัดที่ {index+1} จาก Whole Field · {referenceRois?.[index]?`ตำแหน่ง (${referenceRois[index]!.x1}, ${referenceRois[index]!.y1}) – (${referenceRois[index]!.x2}, ${referenceRois[index]!.y2})`:'ไม่มีพิกัด GT ที่บันทึกไว้'}</span>
     <textarea ref={node=>{if(node)inputs.current.set(index,node);else inputs.current.delete(index);}} className={input} rows={3} aria-label={`Ground Truth ${fieldName(index)}`} placeholder={`ข้อความทั้งหมดภายใน ${fieldName(index)}`} disabled={busy} value={lines[index]??''} onFocus={()=>{setActiveIndex(index);onSelectField?.(index);}} onChange={e=>update(index,e.target.value)}/>
    </label>)}
   </div>}
   <section className="space-y-2 [overflow-anchor:none]" aria-label="พรีวิวข้อความตาม Field"><h3 className="text-sm font-semibold">พรีวิวข้อความ → Field</h3><div className="max-h-64 overflow-auto rounded-lg border border-slate-200">{Array.from({length:lineCount},(_,index)=><div key={index} className="flex items-start gap-3 border-b border-slate-100 p-3 text-sm last:border-b-0" data-testid="gt-field-preview"><span className="min-w-0 flex-1 whitespace-pre-wrap break-words">{lines[index]||<span className="text-slate-400">(ยังไม่มีข้อความ)</span>}</span><button type="button" disabled={busy} className="shrink-0 text-sky-800 underline" onClick={()=>{onMode('per_field');setActiveIndex(index);requestAnimationFrame(()=>{const node=inputs.current.get(index);scrollField(index);node?.focus({preventScroll:true});});}}>{fieldName(index)}</button></div>)}</div></section>
  <div className="flex flex-wrap gap-2">
   <button className="button secondary" disabled={busy} onClick={()=>onSave(false)}>บันทึก GT ฉบับร่าง</button><button className="button primary" disabled={busy||!text.trim()} onClick={()=>onSave(true)}>ยืนยันเพื่อคำนวณ</button>
  </div>
 </section>;
}
