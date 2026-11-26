import type {PipelineRun} from '@/types';
import {textLines} from './full-image-lines';

const valid=(value:unknown):value is number=>typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=1;

/** Match stored recognition segments to original text, without guessing line order. */
export function lineConfidences(run:PipelineRun):(number|null)[]{
 const text=textLines(run.final_text??'').join('\n');
 const empty=textLines(text).map(()=>null);
 if(run.status!=='success'||run.fields?.length!==1)return empty;
 const field=run.fields[0],boxes=field.diagnostics?.boxes;
 if(!Array.isArray(boxes)||!boxes.length){
  return empty.length===1&&valid(field.confidence)?[field.confidence]:empty;
 }
 const scores:number[][]=empty.map(()=>[]);
 let cursor=0;
 for(const box of boxes){
  if(!box||typeof box.text!=='string')return empty;
  const segment=textLines(box.text).join('\n').trim();
  if(!segment)continue;
  while(cursor<text.length&&/\s/.test(text[cursor]))cursor++;
  if(!text.startsWith(segment,cursor))return empty;
  const start=text.slice(0,cursor).split('\n').length-1;
  const score=valid(box.rec_confidence)?box.rec_confidence:box.confidence;
  if(valid(score))segment.split('\n').forEach((part:string,index:number)=>{
   if(part.trim())scores[start+index].push(score);
  });
  cursor+=segment.length;
 }
 if(text.slice(cursor).trim())return empty;
 return scores.map(values=>values.length?values.reduce((sum,value)=>sum+value,0)/values.length:null);
}
