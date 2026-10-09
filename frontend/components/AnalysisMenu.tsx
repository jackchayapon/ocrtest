"use client";
import {useId,useState} from "react";
import {Highlighter,ChevronDown} from "lucide-react";
export type AnalysisMode={highlight:boolean;details:boolean};
export const defaultAnalysis:AnalysisMode={highlight:false,details:false};
export default function AnalysisMenu({name,value,onChange}:{name:string;value:AnalysisMode;onChange:(value:AnalysisMode)=>void}){
 const id=useId();
 const active=value.highlight||value.details;
 const [position,setPosition]=useState({left:0,top:0});
 return <><button type="button" aria-label={`Error Analysis ${name}`} aria-pressed={active} popoverTarget={id} onClick={e=>{const r=e.currentTarget.getBoundingClientRect();setPosition({left:Math.max(8,Math.min(r.left,window.innerWidth-248)),top:r.bottom+4});}} className={`flex items-center gap-1 rounded-lg border px-2 py-1.5 text-xs ${active?"border-indigo-400 bg-indigo-100 text-indigo-900":"border-slate-300 bg-white text-slate-600"}`}><Highlighter size={14}/>Error Analysis<ChevronDown size={12}/></button>
 <div id={id} popover="auto" style={{...position,margin:0}} className="fixed w-60 rounded-lg border border-slate-200 bg-white p-2 shadow-xl">
 <p className="px-2 py-1 text-xs text-slate-500">เปิดพร้อมกันได้ทั้งสองแบบ</p>
 {([["highlight","HIGHLIGHT"],["details","Deep detail"]] as const).map(([mode,label])=><label key={mode} className="flex cursor-pointer items-center gap-2 rounded p-2 text-sm hover:bg-indigo-50"><input type="checkbox" checked={value[mode]} onChange={e=>onChange({...value,[mode]:e.target.checked})}/>{label}</label>)}
 </div></>;
}
