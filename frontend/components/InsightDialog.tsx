"use client";
import {useEffect,useId,useRef} from "react";
export default function InsightDialog({title,onClose,children}:{title:string;onClose:()=>void;children:React.ReactNode}){
 const ref=useRef<HTMLDialogElement>(null),id=useId();
 useEffect(()=>{const el=ref.current;const previous=document.activeElement;el?.showModal();return()=>{el?.close();if(previous instanceof HTMLElement)previous.focus();};},[]);
 return <dialog ref={ref} aria-labelledby={id} onCancel={e=>{e.preventDefault();e.stopPropagation();onClose();}} className="fixed inset-0 m-auto max-h-[94dvh] w-[96vw] max-w-5xl overflow-auto rounded-xl border border-slate-200 bg-white p-4 shadow-xl backdrop:bg-slate-950/50">
 <header className="sticky top-0 z-30 mb-4 flex items-center justify-between gap-4 bg-white py-2"><h2 id={id}>{title}</h2><button autoFocus type="button" className="button secondary" onClick={onClose}>ปิด</button></header>{children}</dialog>;
}
