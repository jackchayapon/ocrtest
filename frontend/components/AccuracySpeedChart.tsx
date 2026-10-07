"use client";
import {useState} from "react";
import {BarChart3, ArrowDownLeft} from "lucide-react";
import type {Decision} from "@/types/comparison";
import {percent} from "@/components/MatrixTable";

const number = (n:number) => n.toLocaleString("th-TH",{maximumFractionDigits:2});
// Identity-based color stays stable when names or response ordering change.
export function pipelineColor(id:string) {
  let hash=2166136261;
  for(const c of id) hash=Math.imul(hash^c.charCodeAt(0),16777619);
  return `hsl(${(hash>>>0)%360} 72% 38%)`;
}
function ticks(max:number) {
  const raw=Math.max(max,0.001)/4, magnitude=10**Math.floor(Math.log10(raw));
  const step=[1,2,2.5,5,10].map(n=>n*magnitude).find(n=>n>=raw)!;
  return Array.from({length:5},(_,i)=>step*i);
}
export default function AccuracySpeedChart({decision}:{decision:Decision}) {
  const s=decision.scatter;
  const [focused,setFocused]=useState<string|null>(null);
  const all=[...s.points].sort((a,b)=>a.pipeline_id.localeCompare(b.pipeline_id));
  const points=all.filter(p=>p.cer!==null&&Number.isFinite(p.cer)&&p.cer>=0&&p.time_seconds!==null&&Number.isFinite(p.time_seconds)&&p.time_seconds>=0);
  const xt=ticks(Math.max(0.1,...points.map(p=>p.time_seconds!))*1.1), yt=ticks(Math.max(0.1,...points.map(p=>p.cer!*100))*1.1);
  const x=(n:number)=>75+n/xt[4]*440,y=(n:number)=>315-n*100/yt[4]*255;
  const frontier=points.filter(p=>p.active&&p.pareto).sort((a,b)=>a.time_seconds!-b.time_seconds!);
  const showPareto=s.pareto_valid&&frontier.length>=2;
  // A single Pareto point cannot form a visible line. The fallback is only a visual guide.
  const guide=points.length>=2&&!showPareto?[...points].sort((a,b)=>a.time_seconds!-b.time_seconds!):[];
  const selected=all.find(p=>p.pipeline_id===focused);
  const description=(p:typeof all[number])=>`${p.pipeline_name} · CER ${percent(p.cer)} · ${p.time_seconds===null?"—":number(p.time_seconds)} วินาที · ${p.documents} เอกสารที่ประเมิน`;
  return <section className="comparison-speed" aria-label="ความแม่นยำ × ความเร็ว">
    <h2><BarChart3 size={22}/> ความแม่นยำ × ความเร็ว</h2>
    <p className="comparison-subtitle">ยิ่งอยู่ใกล้มุมซ้ายล่างยิ่งดี — อ่านผิดน้อยและประมวลผลเร็ว</p>
    {!s.pareto_valid&&<p className="filter-note">{s.cohort_mode==="own"?"ชุดเอกสารไม่ตรงกัน เทียบกันตรง ๆ ไม่ได้":"เวลาของบาง Pipeline ไม่ครบ จึงยังไม่แสดงแนว Pareto"}</p>}
    <div className="comparison-speed-grid">
      <div className="comparison-speed-plot">
        {points.length?<svg role="img" aria-label="กราฟ CER เฉลี่ยกับเวลาเฉลี่ยต่อชุดทดสอบ" viewBox="0 0 560 355">
          {xt.map(t=><g key={`x${t}`}><line data-testid="chart-grid" x1={x(t)} y1="60" x2={x(t)} y2="315" stroke="#e5edf5"/><text x={x(t)} y="338" textAnchor="middle" fontSize="20" fill="#64748b">{number(t)}</text></g>)}
          {yt.map(t=><g key={`y${t}`}><line data-testid="chart-grid" x1="75" y1={y(t/100)} x2="515" y2={y(t/100)} stroke="#e5edf5"/><text x="62" y={y(t/100)+5} textAnchor="end" fontSize="20" fill="#64748b">{number(t)}</text></g>)}
          <path data-testid="chart-axes" d="M75 60 V315 H515" fill="none" stroke="#94a3b8" strokeWidth="1.5"/>
          <text transform="translate(20 185) rotate(-90)" textAnchor="middle" fontSize="20" fill="#334155">CER เฉลี่ย (%)</text>
          {showPareto&&<polyline data-testid="pareto-frontier" points={frontier.map(p=>`${x(p.time_seconds!)},${y(p.cer!)}`).join(" ")} fill="none" stroke="#0667e8" strokeWidth="3" strokeDasharray="7 5" vectorEffect="non-scaling-stroke"/>}
          {guide.length>0&&<polyline data-testid="distribution-guide" aria-label="เส้นช่วยอ่านกราฟ (ไม่ใช่ Pareto)" points={guide.map(p=>`${x(p.time_seconds!)},${y(p.cer!)}`).join(" ")} fill="none" stroke="#94a3b8" strokeWidth="2.5" vectorEffect="non-scaling-stroke"/>}
          {points.map(p=>{const index=all.findIndex(a=>a.pipeline_id===p.pipeline_id)+1;return <g key={p.pipeline_id} tabIndex={0} role="img" aria-label={description(p)} onFocus={()=>setFocused(p.pipeline_id)} onBlur={()=>setFocused(null)} onMouseEnter={()=>setFocused(p.pipeline_id)} onMouseLeave={()=>setFocused(null)} data-testid="chart-marker">
            <title>{description(p)}</title><circle cx={x(p.time_seconds!)} cy={y(p.cer!)} r="14" fill={p.filled?pipelineColor(p.pipeline_id):"white"} stroke={pipelineColor(p.pipeline_id)} strokeWidth="3"/>
            <text x={x(p.time_seconds!)} y={y(p.cer!)+5} textAnchor="middle" fontSize="15" fontWeight="700" fill={p.filled?"white":pipelineColor(p.pipeline_id)}>{index}</text>
          </g>;})}
        </svg>:<p className="comparison-empty">ยังไม่มีผลที่มีทั้ง CER และเวลา ยืนยัน Ground Truth และรัน OCR เพื่อดูกราฟ</p>}
        {points.length>0&&<p className="comparison-speed-axis">เวลาเฉลี่ยต่อชุดทดสอบ (วินาที)</p>}
        <p className="comparison-speed-direction"><ArrowDownLeft size={18}/> มุมซ้ายล่างดีกว่า · CER และเวลาต่ำ</p>
        <p className="comparison-speed-tooltip" role="status">{selected?description(selected):"เลือกจุดด้วยเมาส์หรือแป้นพิมพ์เพื่อดูรายละเอียด"}</p>
      </div>
      <div><h3>Pipeline ทั้งหมด ({all.length} รายการ)</h3><ol className="comparison-speed-legend">{all.map((p,i)=><li key={p.pipeline_id}>
        <span className="comparison-speed-number" style={{background:pipelineColor(p.pipeline_id)}}>{i+1}</span><div><strong>{p.pipeline_name}</strong><span>CER {percent(p.cer)} · {p.time_seconds===null?"—":number(p.time_seconds)} sec</span><small>{p.documents} เอกสาร · {p.cohort_mode==="common"?"เอกสารร่วมกัน":"เอกสารของ Pipeline นี้"}{!p.active?" · เก็บถาวร":""}{!points.includes(p)?" · ข้อมูลยังไม่ครบ":""}</small></div>
      </li>)}</ol>{showPareto&&<p className="comparison-speed-pareto"><span/> แนว Pareto</p>}
      {guide.length>0&&<p className="comparison-speed-pareto" data-testid="distribution-guide-legend"><span style={{borderTop:"2.5px solid #94a3b8"}}/> เส้นช่วยอ่านกราฟ (ไม่ใช่ Pareto)</p>}
      <p className="filter-note">จุดโปร่ง: หลักฐานยังไม่ครบ · เวลาของ Global workflow รวมเวลา Field</p></div>
    </div>
  </section>;
}
