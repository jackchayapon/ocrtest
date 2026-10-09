"use client";
import {useId,useState} from "react";
import type {FieldComparison} from "@/types";
import {errorAnalysisLines} from "@/lib/error-analysis-lines";
import {highlightUnits,type HighlightUnit} from "@/lib/highlight-units";
import {describeCharacters} from "@/lib/character-description";

function ErrorToken({unit}:{unit:HighlightUnit}){
 const id=useId();
 const [position,setPosition]=useState({left:0,top:0});
 if(!unit.errors.length)return <span data-testid="highlight-correct" className="rounded-sm bg-green-100 text-green-900">{unit.text}</span>;
 return <><button type="button" popoverTarget={id} aria-label={`ดูข้อผิดพลาด: ${unit.text}`} data-testid="highlight-error" className="rounded-sm bg-red-100 text-red-800 underline decoration-red-500 decoration-2 underline-offset-4 hover:bg-red-200 focus-visible:outline-2 focus-visible:outline-red-600" style={{font:"inherit",lineHeight:"inherit",minWidth:unit.text==="▏"?8:undefined}} onClick={e=>{const r=e.currentTarget.getBoundingClientRect();setPosition({left:Math.max(8,Math.min(r.left,window.innerWidth-296)),top:Math.min(r.bottom+4,window.innerHeight-200)});}}>{unit.text}</button>
 <div id={id} popover="auto" style={{...position,margin:0}} className="fixed max-h-48 w-72 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-red-200 bg-white p-3 text-sm text-slate-800 shadow-xl"><strong>รายละเอียดข้อผิดพลาด</strong>{unit.errors.map((error,i)=><p key={i} className="mt-2">{error.kind==="deletion"?`ขาด: ${describeCharacters(error.missing??"")}`:error.kind==="insertion"?`อ่านเกิน: ${describeCharacters(error.text)}`:`อ่านผิด: ${describeCharacters(error.text)} → ควรเป็น: ${describeCharacters(error.missing??"")}`}</p>)}</div></>;
}
export default function InteractiveErrorText({evaluation,groundTruth}:{evaluation:FieldComparison;groundTruth:string}){
 const lines=errorAnalysisLines(evaluation,groundTruth)??[{spans:evaluation.spans}];
 return <div data-testid="highlight-output" className="whitespace-pre-wrap break-words leading-relaxed">{lines.map((line,i)=><div key={i} className="min-h-6">{highlightUnits(line.spans).map((unit,j)=><ErrorToken key={j} unit={unit}/>)}</div>)}</div>;
}
