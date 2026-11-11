"use client";
import {useEffect,useState} from "react";

/** GET-only retries: bounded by both attempts and a deadline; never starts OCR. */
export function usePreviewSource(url:string){
 const [retry,setRetry]=useState(0),[state,setState]=useState<{url:string;src?:string;error?:string}>({url:""});
 useEffect(()=>{
  const controller=new AbortController();let disposed=false,objectURL:string|undefined;
  const deadline=setTimeout(()=>controller.abort(),30_000);
  const pause=(ms:number)=>new Promise<void>((resolve,reject)=>{
   if(controller.signal.aborted){reject(new Error("cancelled"));return;}
   const abort=()=>{clearTimeout(timer);reject(new Error("cancelled"));};
   const timer=setTimeout(()=>{controller.signal.removeEventListener("abort",abort);resolve();},ms);
   controller.signal.addEventListener("abort",abort,{once:true});
  });
  async function load(){
   try{
    setState({url});
    for(let attempt=0;attempt<5;attempt++){
     const response=await fetch(url,{signal:controller.signal,cache:"no-store"});
     if([429,503,502,504,408].includes(response.status)&&attempt<4){
      const value=response.headers.get("Retry-After"),seconds=value&&Number.isFinite(Number(value))?Number(value):value?Math.max(0,(Date.parse(value)-Date.now())/1000):2;
      await pause(Math.max(500,Math.min(30_000,Number.isFinite(seconds)?seconds*1000:2000)));continue;
     }
     if(!response.ok)throw new Error(response.status===404?"ไม่พบไฟล์ต้นฉบับ กรุณากู้ไฟล์หรืออัปโหลดใหม่":"ภาพยังไม่พร้อมใช้งาน กรุณาลองโหลดอีกครั้ง");
     const blob=await response.blob();if(disposed)return;
     objectURL=URL.createObjectURL(blob);setState({url,src:objectURL});return;
    }
   }catch(e){if(!disposed)setState({url,error:controller.signal.aborted?"รอโหลดภาพครบกำหนดแล้ว กรุณาลองอีกครั้ง":e instanceof Error?e.message:"โหลดภาพไม่สำเร็จ"});}
   finally{clearTimeout(deadline);}
  }
  void load();return()=>{disposed=true;controller.abort();clearTimeout(deadline);if(objectURL)URL.revokeObjectURL(objectURL);};
 },[url,retry]);
 return {src:state.url===url?state.src:undefined,error:state.url===url?state.error:undefined,retry:()=>setRetry(n=>n+1)};
}
