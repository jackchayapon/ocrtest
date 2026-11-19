import type {EvaluationMode,PipelineRun} from '@/types';
import {textLines} from '@/lib/full-image-lines';
import {pipelineLabel} from '@/lib/i18n/th';
import {useRef,useState} from 'react';

type Props={text:string;runs:PipelineRun[];busy:boolean;mode:EvaluationMode;onMode:(mode:EvaluationMode)=>void;onChange?:(text:string)=>void;onSave?:(calculate:boolean)=>void;onEdit?:()=>void;onWhole?:()=>void;confirmed?:boolean};
const percent=(value:number|null|undefined)=>value==null?'—':`${(value*100).toFixed(2)}%`;

export default function FullImageLineFields({text,runs,busy,mode,onMode,onChange,onSave,onEdit,onWhole,confirmed}:Props){
 const [activeIndex,setActiveIndex]=useState(0);
 const inputs=useRef(new Map<number,HTMLTextAreaElement>());
 const whole=mode==='whole_document';
 const lines=textLines(text);
 const lineCount=Math.max(lines.length,...runs.map(run=>textLines(run.final_text??'').length));
 const fieldName=(index:number)=>`Field ${String(index+1).padStart(2,'0')}`;
 const card='block rounded-xl border bg-slate-50 p-4 space-y-3 focus-within:border-sky-600 focus-within:ring-2 focus-within:ring-sky-600/25';
 const input='textarea w-full rounded-lg border border-slate-300 bg-white p-3 focus:border-sky-600 focus:outline-none focus:ring-2 focus:ring-sky-600/30';
 const gt=whole?[text]:textLines(text),predictions=runs.map(run=>whole?[run.final_text??'']:textLines(run.final_text??''));
 const count=Math.max(gt.length,...predictions.map(lines=>lines.length));
 function update(index:number,value:string){
  if(whole){onChange?.(value);return;}
  const next=[...gt];
  while(next.length<=index)next.push('');
  next[index]=value;
  onChange?.(next.join('\n'));
 }
 return <section className="panel panel-body space-y-4" data-testid="full-image-line-fields">
  {!onChange&&<h2>ผลประเมินและเปรียบเทียบ</h2>}
  <div className="flex gap-2" aria-label="Evaluation mode">{(['whole_document','per_field'] as const).map(value=><button key={value} className={`button ${mode===value?'primary':'secondary'}`} disabled={busy} aria-pressed={mode===value} onClick={()=>onMode(value)}>{value==='whole_document'?'Whole Field':'Sub-fields'}</button>)}</div>
  <p className="text-sm text-slate-600">Whole Field แสดงข้อความทั้งหน้า · Sub-fields แยกจากข้อความ Whole Field ตามการขึ้นบรรทัดใหม่ โดยจับคู่ GT และ OCR ตามลำดับบรรทัด</p>
  {!whole&&predictions.some(lines=>lines.length!==gt.length)&&<p role="status" className="notice-banner">จำนวนบรรทัด GT และ OCR ไม่เท่ากัน ช่องที่ไม่มีบรรทัดคู่กันจะแสดงว่าง กรุณาตรวจลำดับก่อนยืนยัน</p>}
  {onChange?<>
   {whole?<label className={`${card} border-slate-300`} data-testid="whole-gt-card">Ground Truth ทั้งเอกสาร<textarea className={input} rows={10} aria-label="Ground Truth ทั้งเอกสาร" disabled={busy} value={text} onChange={e=>onChange(e.target.value)}/></label>:<div role="region" aria-label="ช่องกรอก Ground Truth ตาม Field" className="max-h-[65vh] space-y-3 overflow-y-auto overscroll-contain p-1">
    {Array.from({length:lineCount},(_,index)=><label key={index} className={`${card} ${index===activeIndex?'ring-2 ring-violet-500':''} ${lines[index]?.trim()?'border-slate-300':'border-red-500'}`} data-testid="field-gt-input">
     <span className="flex items-start justify-between gap-2"><span>{fieldName(index)}</span>{!lines[index]?.trim()&&<span className="text-xs text-red-700">ยังไม่มี GT</span>}</span>
     <span className="block text-xs text-slate-500">บรรทัดที่ {index+1} จาก Whole Field</span>
     <textarea ref={node=>{if(node)inputs.current.set(index,node);else inputs.current.delete(index);}} className={input} rows={3} aria-label={`Ground Truth ${fieldName(index)}`} placeholder={`ข้อความทั้งหมดภายใน ${fieldName(index)}`} disabled={busy} value={lines[index]??''} onFocus={()=>setActiveIndex(index)} onChange={e=>update(index,e.target.value)}/>
    </label>)}
   </div>}
   <section className="space-y-2 [overflow-anchor:none]" aria-label="พรีวิวข้อความตาม Field"><h3 className="text-sm font-semibold">พรีวิวข้อความ → Field</h3><div className="max-h-64 overflow-auto rounded-lg border border-slate-200">{Array.from({length:lineCount},(_,index)=><div key={index} className="flex items-start gap-3 border-b border-slate-100 p-3 text-sm last:border-b-0" data-testid="gt-field-preview"><span className="min-w-0 flex-1 whitespace-pre-wrap break-words">{lines[index]||<span className="text-slate-400">(ยังไม่มีข้อความ)</span>}</span><button type="button" disabled={busy} className="shrink-0 text-sky-800 underline" onClick={()=>{onMode('per_field');setActiveIndex(index);requestAnimationFrame(()=>{const node=inputs.current.get(index);node?.scrollIntoView({block:'nearest'});node?.focus({preventScroll:true});});}}>{fieldName(index)}</button></div>)}</div></section>
  </>:<div className="max-h-[65vh] overflow-auto" tabIndex={0} role="region" aria-label={whole?'Whole Field':'Fields ตามบรรทัด'}>
   <table className="w-full border-collapse text-sm"><thead><tr><th className="border p-3">Field</th><th className="min-w-60 border p-3">Ground Truth</th>{runs.map(run=><th key={run.id} className="min-w-60 border p-3">{pipelineLabel(run.pipeline_id,run.pipeline_name)}</th>)}</tr></thead>
    <tbody>{Array.from({length:count},(_,index)=><tr key={index} data-testid="line-field-row">
     <th className="border p-3 align-top">{whole?'Whole Field':`Field ${String(index+1).padStart(2,'0')}`}</th>
     <td className="border p-3 align-top whitespace-pre-wrap">{gt[index]||'(ว่าง)'}</td>
     {runs.map((run,i)=>{const metric=confirmed?(whole?run.document_evaluation:run.document_evaluation?.line_evaluations?.[index]):undefined;return <td key={run.id} className="border p-3 align-top"><p className="whitespace-pre-wrap" data-testid="line-prediction">{run.status==='error'?'OCR ไม่สำเร็จ':predictions[i][index]||'(ว่าง)'}</p>{!onChange&&run.status!=='error'&&(metric?<p className="mt-2 text-xs text-slate-500">CER {percent(metric.cer)} · WER {percent(metric.wer)} · Exact Match {metric.exact_match?'✓':'✕'}</p>:<p className="mt-2 text-xs text-slate-500">ยืนยันคำนวณใหม่เพื่อดูคะแนน</p>)}</td>;})}
    </tr>)}</tbody>
   </table>
  </div>}
  <div className="flex flex-wrap gap-2">
   {onSave&&<><button className="button secondary" disabled={busy} onClick={()=>onSave(false)}>บันทึก GT ฉบับร่าง</button><button className="button primary" disabled={busy||!text.trim()} onClick={()=>onSave(true)}>ยืนยันเพื่อคำนวณ</button></>}
   {onEdit&&<button className="button secondary" disabled={busy} onClick={onEdit}>กลับไปแก้ Ground Truth</button>}
   {onWhole&&<button className="button secondary" disabled={busy} onClick={onWhole}>ดูผลรวมทั้งภาพ / ส่งออก</button>}
  </div>
 </section>;
}
