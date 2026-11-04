"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { ArrowRight, ArrowLeftRight, BarChart3, Check, ChevronLeft, ChevronRight, Circle, Eye, FileText, Info, Scale, Trophy, Zap } from "lucide-react";
import type { Comparison, Identity } from "@/types/comparison";
import type { MatrixRow, PipelineConfig, TestCase, FieldComparison } from "@/types";
import { assetUrl, cropUrl, getTestCase } from "@/lib/api";
import { comparisonExamples, type ComparisonExample } from "@/lib/comparison-examples";
import { percent } from "@/components/MatrixTable";
import { Scatter, verdict } from "@/components/ComparisonDecision";
import {pipelineModelDisplay} from "@/lib/pipeline-model-label";
import ErrorAnalysisText from "@/components/ErrorAnalysisText";
import {AlignmentRows, AlignmentSummary, AlignmentLegend, alignmentUnavailable} from "@/components/CanonicalAlignment";

const speed = (ms: number | null | undefined) => ms == null ? "—" : `${(ms/1000).toLocaleString("en",{maximumFractionDigits:2})} sec`;
const reliability = (r?: MatrixRow) => r && r.tests > 0 ? percent(r.successful_runs/r.tests) : "—";
const name = (id: string | null, p: Identity[]) => p.find(x => x.pipeline_id === id)?.pipeline_name ?? "—";
function Metric({label,value,note,context}:{label:string;value:string;note:string;context?:string}) {
  return <div className="comparison-metric"><span title={context}>{label}</span><strong>{value}</strong><small>{note}</small></div>;
}

export function ComparisonHero({data,rows,onCompare}:{data:Comparison;rows:MatrixRow[];onCompare:()=>void}) {
  const d=data.overall, p=d.featured_pair, winner=d.recommendation, leader=winner ?? d.ranking[0]?.pipeline_id ?? null;
  const row=rows.find(r=>r.pipeline_id===leader);
  const cer=p && leader ? p.a===leader?p.mean_cer_a:p.b===leader?p.mean_cer_b:null:null;
  const strength=!p || !d.readiness.valid_pair || !p.documents ? "Insufficient"
    : p.documents<data.minimum_documents || p.verdict==="insufficient" ? "Limited"
    : winner && p.winner===winner && p.verdict==="clear" ? "Strong" : "Moderate";
  const strong=strength==="Strong";
  const competitor=p && leader ? name(p.a===leader?p.b:p.a,data.pipelines) : "—";
  const evidenceContext="ระดับหลักฐานจากเอกสารที่คู่หลักมีผลยืนยันพร้อมเทียบ จำนวนเอกสารขั้นต่ำ และข้อสรุปจากระบบ ไม่ใช่ Model confidence ของ OCR";
  const empty=!data.latest_results;
  return <section className="comparison-card comparison-hero" data-testid="comparison-hero" aria-label="คำแนะนำปัจจุบัน">
    <div className="comparison-hero-main">
      {winner && <span className="comparison-recommended"><Trophy size={17}/> แนะนำ</span>}
      <h2>{!data.pipelines.length?"ยังไม่มี Pipeline สำหรับเปรียบเทียบ":empty?"ยังไม่มีผลทดสอบ OCR":winner?name(winner,data.pipelines):"ยังไม่มี Pipeline ที่ชนะชัดเจน"}</h2>
      {winner && <span className="badge info">ดีที่สุดโดยรวม</span>}
      <p className="comparison-subtitle">{winner && p?.mean_dcer_pp!=null?`บนเอกสารที่เทียบตรงกัน อ่านผิดน้อยกว่า ${competitor} ประมาณ ${Math.abs(p.mean_dcer_pp).toFixed(2)} จุดเปอร์เซ็นต์`:empty?"เริ่มทดสอบ OCR และยืนยัน Ground Truth เพื่อเปรียบเทียบ":leader&&cer!==null?`${name(leader,data.pipelines)} นำเชิงตัวเลข แต่ยังไม่มีข้อสรุปผู้ชนะ`:d.readiness.reason ?? "ยังไม่มี Ground Truth ที่ยืนยันแล้ว"}</p>
      <div className="comparison-metrics" data-testid="comparison-simple-cards">
        <Metric label="Paired CER" value={percent(cer)} note="Character Error · เอกสารที่คู่หลักมีผลพร้อมเทียบ" context="เฉลี่ย CER ภายในแต่ละเอกสารก่อน แล้วเฉลี่ยเอกสารที่ทั้งคู่มี GT ยืนยันและผลพร้อมเทียบ PDF หลายหน้านับเป็นเอกสารเดียว"/>
        <Metric label="Speed (average)" value={speed(row?.avg_time_ms)} note="ผลสำเร็จล่าสุดในข้อมูลทั้งหมด · ไม่จำกัดคู่หลัก" context="ค่าเฉลี่ยเวลาที่บันทึกของผลสำเร็จล่าสุด ไม่จำกัดเฉพาะผลที่ยืนยัน GT; Global รุ่นใหม่ใช้เวลาที่ผ่านไปจริงตั้งแต่ Field แรกถึง Field สุดท้ายของ Pipeline รวมเวลารอคิวระหว่างกลุ่ม ประวัติเก่ายังคงค่ารวมเวลา Field เดิม จึงควรเทียบผลจากรุ่นเวลาเดียวกัน"/>
        <Metric label="Reliability" value={reliability(row)} note={row?`${row.successful_runs} / ${row.tests} successful · ผลล่าสุดในข้อมูลทั้งหมด`:"ยังไม่มีผลรัน"} context="ผลสำเร็จ / ผลล่าสุดทั้งหมดต่อชุดทดสอบของ Pipeline นี้ในข้อมูลทั้งหมด ไม่ใช่ประวัติการลองรันทุกครั้ง และไม่จำกัดคู่หลักหรือ GT"/>
        <Metric label="Tested on" value={`${p?.documents ?? 0} documents`} note={`เอกสารชุดเดียวกัน · ${p?.test_cases ?? 0} ชุดทดสอบ`}/>
      </div>
      {empty && <Link className="button primary" href={data.pipelines.length?"/":"/settings/pipelines"}>{data.pipelines.length?"เริ่มทดสอบ OCR":"ไปที่ตั้งค่า Pipeline"}</Link>}
    </div>
    <div className="comparison-evidence"><p>Evidence strength <span tabIndex={0} role="img" aria-label={evidenceContext} title={evidenceContext}><Info size={14}/></span></p><strong className={strong?"comparison-good":""} data-testid="evidence-strength"><span className="comparison-evidence-dots" aria-hidden="true">{[0,1,2,3].map(i=><Circle key={i} size={14} fill={i<(strong?3:strength==="Moderate"?2:strength==="Limited"?1:0)?"currentColor":"none"}/>)}</span>{strength}</strong><small>{p?.documents??0} เอกสารที่เทียบตรงกัน · ขั้นต่ำ {data.minimum_documents}<br/>{strong?"ระบบแนะนำผู้ชนะจากหลักฐานคู่หลัก":strength==="Moderate"?"มีข้อมูลครบขั้นต่ำ แต่ยังไม่สรุปผู้ชนะโดยรวม":"หลักฐานยังไม่เพียงพอ"}</small>
      <div className="comparison-why"><h3>{winner?"Why this pipeline?":"หลักฐานที่มีตอนนี้"}</h3><p><Check size={15}/> {winner?"ชนะบนชุดเอกสารที่เปรียบเทียบได้":"ยังไม่ประกาศผู้ชนะจาก CER เชิงพรรณนา"}</p>{p&&<div data-testid="hero-paired-evidence"><strong>Paired comparison</strong><p>{name(p.a,data.pipelines)} · Paired CER {percent(p.mean_cer_a)}</p><p>{name(p.b,data.pipelines)} · Paired CER {percent(p.mean_cer_b)}</p><p>ส่วนต่าง A − B: {p.mean_dcer_pp==null?"—":`${p.mean_dcer_pp.toFixed(2)} pp`}</p></div>}<p><Check size={15}/> เทียบเอกสารชุดเดียวกัน {p?.documents??0} ฉบับ</p><p><Info size={15}/> ต้องมีอย่างน้อย {data.minimum_documents} เอกสาร และผ่านเกณฑ์การเทียบคู่</p></div>
      <button className="button primary" onClick={onCompare} disabled={data.pipelines.length<2}><Scale size={16}/> Compare with another pipeline <ArrowRight size={16}/></button>
      <a className="button secondary" href="#comparison-errors"><Eye size={16}/> See example errors</a>
    </div>
  </section>;
}

function PipelineDetails({config}:{config?:PipelineConfig}) {
  if(!config)return <p className="filter-note">ข้อมูลในอดีต · ไม่มีการตั้งค่าปัจจุบัน</p>;
  return <details className="comparison-model"><summary title="DET/REC configuration from Pipeline Settings"><Info size={13}/> Model details</summary><p>Pipeline ID: <code>{config.pipeline_id}</code></p><p>Engine: {config.source ?? config.engine ?? "—"} · {config.execution_mode ?? "—"}</p>{(["det","rec"] as const).map(kind=>{
    const m=pipelineModelDisplay(config,kind);
    return <div key={kind}><strong>{kind==="det"?"Text Detection":"Text Recognition"}</strong><p>{m.name}</p><p>Version: {m.version ?? "—"} · Weight: {m.weight ?? "—"}</p></div>;
  })}</details>;
}

export function PipelineRanking({data,configs,rows,onCompare}:{data:Comparison;configs:PipelineConfig[];rows:MatrixRow[];onCompare:(id:string)=>void}) {
  const ordered=[...data.overall.ranking,...data.pipelines.filter(p=>!data.overall.ranking.some(r=>r.pipeline_id===p.pipeline_id))];
  return <section className="comparison-card comparison-ranking"><h2><BarChart3/> All Pipelines</h2><p className="filter-note">ลำดับจากการเทียบเป็นคู่ · Overall CER ใช้เอกสารที่ Pipeline นี้ประเมินได้เอง จึงอาจต่างจาก Paired CER · เวลาและ Reliability ใช้ผลล่าสุดในข้อมูลทั้งหมด</p>
    <table aria-label="All Pipelines"><thead><tr><th>#</th><th>Pipeline</th><th title="Mean within each document, then mean across this pipeline's eligible documents in current data">Overall CER ↓</th><th title="Latest successful results with timing per test case in current data; not restricted to paired GT">Speed (average) ↓</th><th title="Successful / all latest eligible results per test case in current data">Reliability ↑</th><th title="Distinct eligible documents for Overall CER; PDF pages share a document">Tested Docs</th><th>Actions</th></tr></thead><tbody>{ordered.map((p,i)=>{
      const cell=data.overall.cells.find(c=>c.pipeline_id===p.pipeline_id), r=rows.find(r=>r.pipeline_id===p.pipeline_id), recommended=p.pipeline_id===data.overall.recommendation;
      return <tr key={p.pipeline_id} className={recommended?"comparison-winner":""}><td data-label="Rank"><span className="comparison-rank">{i+1}</span></td><td data-label="Pipeline"><strong>{p.pipeline_name}</strong>{recommended && <span className="comparison-recommended"><Trophy size={12}/> Recommended</span>}{!p.active&&<span className="badge neutral">เก็บถาวร / ปิดใช้งาน</span>}<PipelineDetails config={configs.find(c=>c.pipeline_id===p.pipeline_id)}/></td><td data-label="Overall CER"><strong>{percent(cell?.cer ?? null)}</strong></td><td data-label="Speed (average)">{speed(r?.avg_time_ms)}</td><td data-label="Reliability">{reliability(r)}<small>{r?`${r.successful_runs} / ${r.tests}`:"—"}</small></td><td data-label="Tested Docs">{cell?.documents??0}</td><td><button className="button secondary" onClick={()=>onCompare(p.pipeline_id)} disabled={data.pipelines.length<2}><BarChart3 size={14}/> Compare</button></td></tr>;
    })}</tbody></table>{!ordered.length&&<p>ยังไม่มี Pipeline สำหรับเปรียบเทียบ <Link href="/settings/pipelines" className="text-link">ไปที่ตั้งค่า Pipeline</Link></p>}
  </section>;
}

export function DocumentTypeWinners({data,onAll}:{data:Comparison;onAll:()=>void}) {
  return <section className="comparison-card comparison-types"><h2><FileText/> Best by Document Type</h2>{data.by_type.filter(g=>g.code!=="unassigned").slice(0,5).map(g=>{
    const id=g.decision.recommendation, p=g.decision.featured_pair;
    const cer=id&&p?(p.a===id?p.mean_cer_a:p.mean_cer_b):null;
    return <div className="comparison-type" key={g.code}><FileText size={22}/><div><strong>{g.name}</strong><span>{id?name(id,data.pipelines):"ยังสรุปไม่ได้"}</span><small>{p?.documents??0} เอกสารที่เทียบตรงกัน{g.archived?" · เก็บถาวร":""}</small></div><span className="comparison-good" title="Paired CER within this document type"><small>Type paired CER</small>{percent(cer)}</span></div>;
  })}{!data.by_type.some(g=>g.code!=="unassigned")&&<p className="filter-note">ยังไม่มีผลแยกตามประเภทเอกสาร</p>}<button className="comparison-link" onClick={onAll}>ดูประเภทเอกสารทั้งหมด <ArrowRight size={14}/></button></section>;
}

function Diff({evaluation,text,gt}:{evaluation:FieldComparison|null;text:string;gt:string}) {
  return evaluation?.spans?<ErrorAnalysisText evaluation={evaluation} groundTruth={gt}/>:<><p className="comparison-text">{text||"—"}</p><small>{alignmentUnavailable}</small></>;
}
function ResultCard({title,text,gt,cer,evaluation,field,pending}:{title:string;text:string;gt:string;cer:number;evaluation:FieldComparison|null;field:boolean;pending:boolean}) {
  return <article className="comparison-result" aria-label={title}><h3>{title}</h3><div className="comparison-result-body">{evaluation?.spans?<><AlignmentRows spans={evaluation.spans}/><AlignmentSummary spans={evaluation.spans}/></>:<><p className="comparison-text">GT: {gt}</p><p className="comparison-text">OCR: {text||"—"}</p><small role="status">{pending?"กำลังโหลดรายละเอียด alignment…":alignmentUnavailable}</small></>}</div><footer>{evaluation?<span>{evaluation.character_edits} character errors</span>:<span>ผลประเมินที่บันทึกไว้</span>}<strong title="CER อาจเกิน 100% ได้เมื่อจำนวนตัวอักษรที่อ่านเกิน/ผิดมากกว่าความยาว Ground Truth">{field?"This field CER":"This document CER"} {percent(cer)}</strong></footer></article>;
}

export function CompactErrorAnalysis({example,title,pending=false}:{example:ComparisonExample|null;title:string;pending?:boolean}) {
  const [tab,setTab]=useState("Character diff");
  const e=example?.evaluationB ?? null;
  return <section className="comparison-card" id="comparison-errors"><h2><FileText/> Error Analysis</h2><p className="comparison-subtitle">ดูรายละเอียดว่าโมเดลผิดตรงไหน</p><div className="comparison-tabs" role="tablist" aria-label="Error Analysis">{["Character diff","Error breakdown","Per-line view"].map(t=><button key={t} role="tab" aria-selected={tab===t} onClick={()=>setTab(t)}>{t}</button>)}</div>{example?<div role="tabpanel"><span className="badge neutral">{title}</span><p className="filter-note">{example.fieldId?"This field":"This document"} · {example.testCase.document.filename}</p>{!e?.spans?<><p className="comparison-text">OCR: {example.textB}</p><p className="comparison-text">GT: {example.gt}</p><p role="status">{pending?"กำลังโหลดรายละเอียด alignment…":alignmentUnavailable}</p></>:tab==="Error breakdown"?<AlignmentSummary spans={e.spans}/>:tab==="Per-line view"?<Diff evaluation={e} text={example.textB} gt={example.gt}/>:<AlignmentRows spans={e.spans}/>}</div>:<p className="comparison-empty">เลือกคู่ที่มี Ground Truth ยืนยันและผลพร้อมเปรียบเทียบ</p>}</section>;
}

export function PipelineSideBySide({data,cases,pair,setPair,onNextPage,hasNext}:{data:Comparison;cases:TestCase[];pair:[string,string];setPair:(p:[string,string])=>void;onNextPage:()=>void;hasNext:boolean}) {
  const [selected,setSelected]=useState<string|null>(null), [detail,setDetail]=useState<TestCase|null>(null), [error,setError]=useState(""), [retry,setRetry]=useState(0);
  const examples=comparisonExamples(cases,...pair);
  const candidate=examples.find(e=>e.key===selected)??examples[0]??null;
  const index=candidate?examples.findIndex(e=>e.key===candidate.key):0;
  const caseId=candidate?.testCase.id;
  useEffect(()=>{
    let active=true;
    if(!caseId)return;
    getTestCase(caseId).then(c=>{if(active){setDetail(c);setError("");}}).catch(()=>{if(active){setDetail(null);setError("โหลดรายละเอียดไม่สำเร็จ กรุณาลองใหม่");}});
    return ()=>{active=false;};
  },[caseId,retry]);
  const hydrated=detail && candidate && detail.id===candidate.testCase.id?comparisonExamples([detail],...pair).find(e=>e.key===candidate.key):null;
  // A current detail response can invalidate eligibility (GT cleared or run failed).
  // Never replace that authoritative result with a stale history example.
  const example=detail && candidate && detail.id===candidate.testCase.id ? hydrated ?? null : candidate;
  const p=[...data.overall.pairs,...data.overall.historical_pairs].find(p=>[p.a,p.b].includes(pair[0])&&[p.a,p.b].includes(pair[1])&&pair[0]!==pair[1]);
  const navigate=(key:string)=>setSelected(key);
  return <><section className="comparison-card" id="compare-results" aria-label="เปรียบเทียบสอง Pipeline โดยตรง"><div className="comparison-section-head"><div><h2><Scale/> Compare Results</h2><p className="comparison-subtitle">ดูตัวอย่างผลลัพธ์ของแต่ละ Pipeline แบบ side-by-side</p></div><div className="comparison-pair-controls">
    {([0,1] as const).map(i=><label key={i} className="field">Pipeline {i===0?"A":"B"}<select aria-label={`Pipeline ${i===0?"A":"B"}`} className="select" value={pair[i]} onChange={e=>setPair(i===0?[e.target.value,pair[1]]:[pair[0],e.target.value])}><option value="">เลือก Pipeline</option>{data.pipelines.map(p=><option key={p.pipeline_id} value={p.pipeline_id}>{p.pipeline_name}{p.active?"":" (เก็บถาวร)"}</option>)}</select></label>)}
    <button className="button secondary" aria-label="สลับ Pipeline" onClick={()=>setPair([pair[1],pair[0]])}><ArrowLeftRight size={16}/></button>
    <div className="comparison-navigation"><button className="button secondary" aria-label="ตัวอย่างก่อนหน้า" disabled={!index} onClick={()=>navigate(examples[index-1].key)}><ChevronLeft size={16}/></button><span>{examples.length?index+1:0} / {examples.length}</span><button className="button secondary" aria-label="ตัวอย่างถัดไป" disabled={index>=examples.length-1} onClick={()=>navigate(examples[index+1].key)}><ChevronRight size={16}/></button></div>
  </div></div><p className="filter-note">{p?`เทียบตรงกัน ${p.documents} เอกสาร · ${p.test_cases} ชุดทดสอบ`:"ยังไม่มีข้อมูลคู่นี้สำหรับเปรียบเทียบ"} · การเลือกคู่นี้ไม่เปลี่ยนคำแนะนำของระบบ</p>
  {p&&<p className="font-semibold">{verdict(p,data.pipelines)}</p>}
  {error&&<p role="alert" className="error-banner">{error} <button className="button secondary" onClick={()=>setRetry(n=>n+1)}>ลองโหลดตัวอย่างอีกครั้ง</button></p>}{candidate&&detail?.id!==caseId&&!error&&<p role="status">กำลังโหลดตัวอย่าง…</p>}
  {example?<><div className="comparison-four"><article className="comparison-original"><h3>Original Document</h3><SourceImage key={example.key} example={example}/><span>{example.testCase.document.filename}{example.fieldId?" · Field ROI":""}</span></article><article className="comparison-result"><h3>Ground Truth</h3><p className="comparison-text">{example.gt}</p><small>Ground Truth ที่ยืนยันแล้ว</small></article><ResultCard title={name(pair[0],data.pipelines)} text={example.textA} gt={example.gt} evaluation={example.evaluationA} cer={example.cerA} field={!!example.fieldId} pending={!!candidate && detail?.id!==caseId && !error}/><ResultCard title={name(pair[1],data.pipelines)} text={example.textB} gt={example.gt} evaluation={example.evaluationB} cer={example.cerB} field={!!example.fieldId} pending={!!candidate && detail?.id!==caseId && !error}/></div><AlignmentLegend/></>:<p className="comparison-empty">{pair[0]===pair[1]?"เลือก Pipeline คนละตัว":p && p.documents>0?"ยังไม่พบตัวอย่างที่พร้อมเปรียบเทียบในหน้าประวัติปัจจุบัน":"ยังไม่มีเอกสารชุดเดียวกันที่ Pipeline ทั้งสองมีผลพร้อมเปรียบเทียบ"}<br/>{pair[0]!==pair[1] && p && p.documents>0?`ระบบมีเอกสารที่เทียบตรงกัน ${p.documents} ฉบับ ลองดูหน้าประวัติถัดไป หรือเปิดผลรายชุดทดสอบ`:"ต้องมี Ground Truth ที่ยืนยันแล้วและผลสำเร็จของทั้งสอง Pipeline"}</p>}
  <div className="comparison-section-head"><small>ตัวอย่างจากหน้าประวัติปัจจุบัน · Field ที่ใช้ GT เดียวกันแสดงแยกกัน</small>{hasNext&&<button className="button secondary" onClick={onNextPage}>ดูตัวอย่างจากหน้าถัดไป <ArrowRight size={14}/></button>}</div></section>
  <div className="comparison-bottom"><DisagreementCases data={data} examples={examples} onSelect={navigate} pair={pair}/><CompactErrorAnalysis example={example} title={name(pair[1],data.pipelines)} pending={!!candidate && detail?.id!==caseId && !error}/></div>
  <details className="comparison-card comparison-advanced"><summary>Advanced evaluation details</summary><details><summary>ความแม่นยำ × ความเร็ว</summary><Scatter decision={data.overall}/></details>{example&&<><p className="filter-note">ผลรวมของชุดทดสอบที่มีตัวอย่างนี้ · WER / Exact Match ตามโหมดประเมิน อาจรวมหลาย Field</p><dl className="comparison-breakdown">{[example.a,example.b].map(r=><div key={r.id}><dt>{name(r.pipeline_id,data.pipelines)}</dt><dd>WER {percent(r.metrics?.wer ?? null)} · Exact Match {r.metrics?String(r.metrics.exact_match):"—"}<br/>Model confidence {percent(r.confidence)} · Gateway {speed(r.gateway_duration_ms)}<br/>Request ID: {r.gateway_request_id??"—"}</dd></div>)}</dl></>}<p className="filter-note">Model confidence ไม่ได้ปรับเทียบตรงกันระหว่างโมเดล · WER แบ่งคำด้วย whitespace ซึ่งมีข้อจำกัดสำหรับภาษาไทย</p></details>
  </>;
}
function SourceImage({example}:{example:ComparisonExample}) {
  const [failed,setFailed]=useState(false);
  const url=example.roi?cropUrl(example.testCase.document_id,example.roi,example.testCase.page_number):assetUrl(example.testCase.document.image_url);
  return failed?<p className="comparison-empty">ไฟล์ต้นฉบับไม่พร้อมใช้งาน</p>:<a href={url} target="_blank" rel="noreferrer" aria-label="เปิดภาพต้นฉบับ"><Image unoptimized width={420} height={220} src={url} alt={`Original ${example.testCase.document.filename}`} onError={()=>setFailed(true)}/></a>;
}
function DisagreementCases({data,examples,onSelect,pair}:{data:Comparison;examples:ComparisonExample[];onSelect:(key:string)=>void;pair:[string,string]}) {
  const sorted=[...examples].sort((a,b)=>Math.abs(b.cerA-b.cerB)-Math.abs(a.cerA-a.cerB));
  return <section className="comparison-card"><h2><Zap/> Examples where pipelines disagree most</h2><p className="comparison-subtitle">ผลต่างของคู่ที่เลือกในหน้าประวัติปัจจุบัน</p><div className="comparison-disagreement-heading"><span>Document</span><span>{name(pair[0],data.pipelines)} · Example CER</span><span>{name(pair[1],data.pipelines)} · Example CER</span><span>Difference</span></div>{sorted.slice(0,4).map(e=><div className="comparison-disagreement" key={e.key}><Thumbnail example={e}/><div><strong>{e.testCase.document.filename}</strong><small>{e.testCase.document.document_type_name??"ไม่ระบุประเภท"}</small></div><span title={`${e.fieldId?"This field CER":"This document CER"} - ${name(pair[0],data.pipelines)}`}>{percent(e.cerA)}</span><span title={`${e.fieldId?"This field CER":"This document CER"} - ${name(pair[1],data.pipelines)}`}>{percent(e.cerB)}</span><strong className="comparison-difference">{(Math.abs(e.cerA-e.cerB)*100).toFixed(1)} pp</strong><button className="button secondary" onClick={()=>{onSelect(e.key);document.getElementById("compare-results")?.scrollIntoView({behavior:"smooth"});}}><Eye size={14}/> Inspect</button></div>)}{!sorted.length&&<p className="comparison-empty">ยังไม่มีตัวอย่างที่ทั้งคู่พร้อมเปรียบเทียบ</p>}<details><summary>ดูชุดที่ผลต่างกันมากในขอบเขตทั้งหมด</summary><p className="filter-note">รายการนี้อาจเป็นคู่ Pipeline อื่น · เปิดชุดทดสอบเพื่อดูผล</p>{data.actions.largest_spread.map(c=><p key={c.test_case_id}><Link className="text-link" href={c.href}>{c.filename}</Link> · {c.spread==null?"—":`${(c.spread*100).toFixed(1)} pp`}</p>)}</details></section>;
}
function Thumbnail({example}:{example:ComparisonExample}) {
  const [failed,setFailed]=useState(false);
  if(failed)return <FileText size={22} aria-label="ไฟล์ต้นฉบับไม่พร้อมใช้งาน"/>;
  const url=example.roi?cropUrl(example.testCase.document_id,example.roi,example.testCase.page_number):assetUrl(example.testCase.document.image_url);
  return <Image unoptimized width={40} height={40} className="comparison-thumbnail" src={url} alt="" onError={()=>setFailed(true)}/>;
}
