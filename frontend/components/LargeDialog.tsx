"use client";
import {useEffect,useId,useRef,type ReactNode} from "react";
import {X} from "lucide-react";

export default function LargeDialog({title,onClose,children,back}:{title:string;onClose:()=>void;children:ReactNode;back?:()=>void}){
 const ref=useRef<HTMLDialogElement>(null),id=useId();
 useEffect(()=>{
  let opener=document.activeElement instanceof HTMLElement?document.activeElement:null;
  const popover=opener?.closest<HTMLElement>('[popover]');
  if(popover){opener=document.querySelector<HTMLElement>(`[popovertarget="${CSS.escape(popover.id)}"]`);popover.hidePopover();}
  const el=ref.current,overflow=document.body.style.overflow,padding=document.body.style.paddingRight;
  document.body.style.paddingRight=`${window.innerWidth-document.documentElement.clientWidth+parseFloat(getComputedStyle(document.body).paddingRight)}px`;
  document.body.style.overflow="hidden";el?.showModal();
  return()=>{el?.close();document.body.style.overflow=overflow;document.body.style.paddingRight=padding;opener?.focus({preventScroll:true});};
 },[]);
 return <dialog ref={ref} aria-labelledby={id} onCancel={e=>{e.preventDefault();onClose();}} className="fixed inset-0 m-auto h-[94dvh] max-h-[94dvh] w-[96vw] max-w-none overflow-hidden rounded-xl border border-slate-200 bg-slate-50 p-0 text-slate-800 shadow-xl backdrop:bg-slate-950/50">
 <div className="flex h-full min-w-0 flex-col"><header className="flex shrink-0 items-center justify-between gap-3 border-b bg-white p-4"><div className="min-w-0"><h2 id={id} className="break-words">{title}</h2>{back&&<button className="text-sm text-sky-800 underline" onClick={back}>กลับไปสถิติอักขระ</button>}</div><button type="button" className="button secondary shrink-0" aria-label="ปิดรายละเอียด" onClick={onClose}><X size={18}/>ปิด</button></header><div className="min-h-0 min-w-0 flex-1 overflow-auto overscroll-contain p-4 [overflow-wrap:anywhere]">{children}</div></div>
 </dialog>;
}
