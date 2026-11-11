import {APIError,uploadDocument} from "./api";

/** Retry only an explicit rejection BEFORE the upload route accepted any data. */
export async function uploadWithAdmission(file:File,type:string,signal:AbortSignal,onWait:(seconds:number|null)=>void){
 const deadline=Date.now()+60_000;
 for(let attempt=0;attempt<12;attempt++){
  if(signal.aborted)throw new Error("ยกเลิกการรออัปโหลดแล้ว");
  onWait(null);
  const request=new AbortController(),cancel=()=>request.abort();
  const timer=setTimeout(()=>request.abort(),Math.min(30_000,Math.max(1,deadline-Date.now())));
  signal.addEventListener("abort",cancel,{once:true});
  try{return await uploadDocument(file,type,request.signal);}
  catch(e){
   clearTimeout(timer);
   if(request.signal.aborted)throw new Error("การส่งไฟล์หมดเวลาหรือถูกยกเลิก อาจมีเอกสารบันทึกแล้ว กรุณาตรวจประวัติก่อนอัปโหลดซ้ำ");
   if(!(e instanceof APIError)||e.status>=500)throw new Error("ยังยืนยันการรับไฟล์ไม่ได้ อาจมีเอกสารบันทึกแล้ว กรุณาตรวจประวัติก่อนอัปโหลดซ้ำ");
   if(e.status!==429||!e.retrySafe)throw e;
   const value=e.retryAfter,seconds=value&&Number.isFinite(Number(value))?Number(value):value?(Date.parse(value)-Date.now())/1000:5;
   const wait=Math.max(500,Number.isFinite(seconds)?seconds*1000:5000);
   if(attempt===11||Date.now()+wait>=deadline)throw new Error("ยังรอประมวลผลภาพอยู่ ครบเวลารออัปโหลดแล้ว ยังไม่ได้สร้างเอกสาร กรุณาลองใหม่ภายหลัง");
   onWait(Math.ceil(wait/1000));
   await new Promise<void>((resolve,reject)=>{
    if(signal.aborted){reject(new Error("ยกเลิกการรออัปโหลดแล้ว"));return;}
    const abort=()=>{clearTimeout(timer);reject(new Error("ยกเลิกการรออัปโหลดแล้ว"));};
    const timer=setTimeout(()=>{signal.removeEventListener("abort",abort);resolve();},wait);
    signal.addEventListener("abort",abort,{once:true});
   });
  }
  finally{clearTimeout(timer);signal.removeEventListener("abort",cancel);}
 }
 throw new Error("ครบเวลารออัปโหลด กรุณาลองใหม่ภายหลัง");
}
