"use client";
import {useEffect,useRef,useState,type ReactNode} from 'react';
import LoadingHand from './LoadingHand';
import styles from './EvaluationFeedback.module.css';

export function CalculationPrompt({onCalculate,onBack}:{onCalculate:()=>void;onBack:()=>void}){
 return <FeedbackDialog title="ตรวจครบทุก Pipeline แล้ว" onCancel={onBack}>
  <p>ทุก Pipeline ผ่านการตรวจหรือยืนยันข้อจำกัดแล้ว ต้องการไปคำนวณ CER/WER เลยไหม?</p>
  <div className="mt-5 flex flex-wrap gap-3"><button className="button primary" onClick={onCalculate}>ตรวจครบแล้ว คำนวณ CER/WER</button><button className="button secondary" onClick={onBack}>กลับไปตรวจดู</button></div>
 </FeedbackDialog>;
}

export function EvaluationLoading({completed,total,label,started}:{completed:number;total:number;label:string;started:number}){
 const [elapsed,setElapsed]=useState(0);
 useEffect(()=>{const timer=setInterval(()=>setElapsed(Math.floor((Date.now()-started)/1000)),250);return()=>clearInterval(timer);},[started]);
 const percent=Math.round(completed/total*100);
 const steps=total===3?['บันทึก Ground Truth','ตรวจตำแหน่ง Pipeline','คำนวณ CER / WER']:['บันทึก Ground Truth','คำนวณ CER / WER'];
 return <FeedbackDialog title="กำลังเตรียมและคำนวณ CER/WER" fullScreen>
  <div className={styles.card}>
   <div className={styles.hero}><span className={styles.eyebrow}>OCR BENCHMARK</span><LoadingHand/><h3 className={styles.heroTitle}>กำลังประเมินผลข้อความ</h3><p className={styles.heroText}>เปรียบเทียบผล OCR กับ Ground Truth<br/>เพื่อสรุปผลประเมินของคุณ</p></div>
   <section className={styles.content}>
    <span className={styles.badge}><span className={styles.dot}/>กำลังประมวลผล</span>
    <h2 className={styles.title}>กำลังเตรียมและคำนวณ CER/WER</h2>
    <p role="status" className={styles.status}>{label}</p>
    <div className={styles.progressHeader}><span>ขั้นตอนเสร็จแล้ว {completed}/{total}</span><span className={styles.percent}>{percent}%</span></div>
    <progress aria-label="ความคืบหน้าขั้นตอนประเมิน" value={completed} max={total} className={styles.progress}/>
    <ol className={styles.steps}>{steps.map((step,index)=><li key={step} className={styles.step} data-state={index<completed?'done':index===completed?'current':'pending'} aria-current={index===completed?'step':undefined}><span className={styles.stepNumber}>{index<completed?'✓':index+1}</span>{step}</li>)}</ol>
    <p className={styles.time}>เวลาที่ใช้ {Math.floor(elapsed/60)} นาที {elapsed%60} วินาที</p>
    <p className={styles.note}>เปอร์เซ็นต์อิงขั้นตอนที่เสร็จจริง ระหว่างคำนวณคะแนนระบบกำลังรอผลจากเซิร์ฟเวอร์</p>
   </section>
  </div>
 </FeedbackDialog>;
}

function FeedbackDialog({title,children,onCancel,fullScreen=false}:{title:string;children:ReactNode;onCancel?:()=>void;fullScreen?:boolean}){
 const ref=useRef<HTMLDialogElement>(null);
 useEffect(()=>{const dialog=ref.current;const opener=document.activeElement;dialog?.showModal();return()=>{dialog?.close();if(opener instanceof HTMLElement&&opener.isConnected)opener.focus({preventScroll:true});};},[]);
 return <dialog ref={ref} aria-label={title} onCancel={e=>{e.preventDefault();onCancel?.();}} className={`fixed inset-0 m-auto text-slate-800 shadow-xl backdrop:bg-slate-950/50 ${fullScreen?`h-dvh max-h-none w-screen max-w-none overflow-y-auto ${styles.screen}`:'w-[min(92vw,560px)] rounded-xl bg-white p-8'}`}><div className={fullScreen?styles.center:''}>{!fullScreen&&<h2 className="text-xl font-semibold">{title}</h2>}{children}</div></dialog>;
}
