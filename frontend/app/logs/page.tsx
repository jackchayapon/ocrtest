"use client";
import { useEffect, useState } from "react";
import { getLogs, type AppLog } from "@/lib/api";

export default function LogsPage() {
  const [filters, setFilters] = useState<Record<string,string>>({});
  const [offset, setOffset] = useState(0), [revision,setRevision] = useState(0);
  const [items,setItems] = useState<AppLog[]>([]), [total,setTotal] = useState(0), [error,setError] = useState("");
  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({limit:"25",offset:String(offset)});
    const caseId = new URLSearchParams(window.location.search).get("test_case_id"); if(caseId) params.set("test_case_id",caseId);
    Object.entries(filters).forEach(([key,value]) => {if(value) params.set(key,key.startsWith("date_") ? new Date(value).toISOString() : value);});
    getLogs(params).then(data => {if(active){setItems(data.items);setTotal(data.total);setError("");}}).catch(() => {if(active)setError("โหลดบันทึกไม่สำเร็จ");});
    return () => {active=false;};
  },[filters,offset,revision]);
  function filter(name:string,value:string){setOffset(0);setFilters(old=>({...old,[name]:value}));}
  return <div className="page-stack"><div className="page-heading"><h1>บันทึกการทำงาน</h1><button className="button secondary" onClick={()=>setRevision(n=>n+1)}>รีเฟรช</button></div><p>แสดงเฉพาะสถานะและรหัสอ้างอิง ไม่แสดงข้อความ OCR, Ground Truth หรือข้อมูลลับ</p><section className="panel flex flex-wrap gap-3 p-4">
    <label className="field">ระดับ<select aria-label="ระดับ" className="select" onChange={e=>filter("level",e.target.value)}><option value="">ทั้งหมด</option>{["INFO","WARNING","ERROR"].map(v=><option key={v}>{v}</option>)}</select></label>
    <label className="field">Pipeline<select aria-label="Pipeline" className="select" onChange={e=>filter("pipeline",e.target.value)}><option value="">ทั้งหมด</option>{["mint","hutch_crop","hutch_full"].map(v=><option key={v}>{v}</option>)}</select></label>
    <label className="field">เหตุการณ์<input className="input" placeholder="ocr_run_error" onChange={e=>filter("event_type",e.target.value)} /></label>
    <label className="field">Request ID<input className="input" onChange={e=>filter("request_id",e.target.value)} /></label>
    <label className="field">ตั้งแต่<input type="datetime-local" className="input" onChange={e=>filter("date_from",e.target.value)} /></label><label className="field">ถึง<input type="datetime-local" className="input" onChange={e=>filter("date_to",e.target.value)} /></label>
  </section>{error && <p role="alert">{error}</p>}<div className="panel overflow-auto"><table className="w-full text-left text-xs"><thead><tr>{["เวลา","ระดับ","เหตุการณ์","หน้า","Pipeline","Request ID","สถานะ/ข้อความ"].map(v=><th className="p-3" key={v}>{v}</th>)}</tr></thead><tbody>{items.map(row=><tr key={row.id}><td className="p-3">{new Date(row.created_at).toLocaleString("th-TH")}</td><td>{row.level}</td><td>{row.event_type}</td><td>{row.page_number??"—"}</td><td>{row.pipeline_id??"—"}</td><td className="max-w-48 break-all">{row.request_id??row.gateway_request_id??"—"}</td><td>{row.message} {row.metadata.error_code}</td></tr>)}</tbody></table></div><div className="flex gap-3"><button className="button secondary" disabled={!offset} onClick={()=>setOffset(n=>Math.max(0,n-25))}>ก่อนหน้า</button><span>{total ? offset+1 : 0}–{Math.min(offset+25,total)} / {total}</span><button className="button secondary" disabled={offset+25>=total} onClick={()=>setOffset(n=>n+25)}>ถัดไป</button></div></div>;
}
