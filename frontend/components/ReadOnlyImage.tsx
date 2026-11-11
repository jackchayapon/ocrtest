"use client";
import {useState} from "react";
import {usePreviewSource} from "@/lib/use-preview-source";

export default function ReadOnlyImage({url,alt,className}:{url:string;alt:string;className?:string}){
 const source=usePreviewSource(url),[failed,setFailed]=useState(false);
 return <div>{source.error||failed?<p role="alert">{source.error??"ไม่สามารถแสดงภาพได้"} <button className="underline" onClick={()=>{setFailed(false);source.retry();}}>ลองโหลดภาพอีกครั้ง</button></p>:!source.src?<p role="status">กำลังโหลดภาพ…</p>:
 // Original pixels; no image optimization or backend resampling.
 // eslint-disable-next-line @next/next/no-img-element
 <img src={source.src} alt={alt} className={className} onError={()=>setFailed(true)}/>}</div>;
}
