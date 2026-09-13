"use client";
import { useState } from "react";
import Link from "next/link";
import { runPages, type PageProgress } from "@/lib/api";

export function parsePages(input: string, count: number): number[] {
  const pages = new Set<number>();
  for (const part of input.split(",").map(s => s.trim()).filter(Boolean)) {
    const match = /^(\d+)(?:\s*-\s*(\d+))?$/.exec(part);
    if (!match) throw new Error("ระบุหน้าเช่น 1, 3, 5-8");
    const first = Number(match[1]), last = Number(match[2] ?? match[1]);
    if (first < 1 || last > count || first > last) throw new Error("หมายเลขหน้าไม่ถูกต้อง");
    for (let page = first; page <= last; page++) pages.add(page);
  }
  return [...pages].sort((a, b) => a - b);
}

export default function PdfBatchPanel({ documentId, pageCount, pipelines, categoryCodes, disabled, onBusy }: {
  documentId: string; pageCount: number; pipelines: string[]; categoryCodes: string[]; disabled: boolean; onBusy: (busy: boolean) => void;
}) {
  const [selection, setSelection] = useState("");
  const [states, setStates] = useState<Record<number, PageProgress>>({});
  const [running, setRunning] = useState(false), [error, setError] = useState("");
  let pages: number[] = [], invalid = "";
  try { pages = parsePages(selection, pageCount); } catch (e) { invalid = (e as Error).message; }
  async function start(selected: number[]) {
    if (running || !selected.length) return;
    setRunning(true); onBusy(true); setError("");
    setStates(Object.fromEntries(selected.map(page => [page, { page, event: "queued", status: "queued" }])));
    try { await runPages(documentId, selected, pipelines, categoryCodes, event => {
      if (event.page) setStates(old => ({ ...old, [event.page!]: event }));
    }); } catch (e) { setError((e as Error).message); }
    finally { setRunning(false); onBusy(false); }
  }
  const rows = Object.values(states).sort((a, b) => a.page! - b.page!);
  const current = rows.find(row => row.status === "running");
  const failed = rows.filter(row => row.status === "error").map(row => row.page!);
  return <section className="panel my-4 p-4" aria-label="เลือกหลายหน้า PDF">
    <h2 className="font-semibold">OCR หลายหน้าแบบทีละหน้า</h2>
    <p className="my-2 text-xs text-slate-500">สร้างชุดทดสอบใหม่แบบเต็มหน้า ไม่แก้ ROI หรือ Ground Truth เดิม ใช้ Pipeline และประเภทข้อมูลที่เลือกด้านขวากับทุกหน้า ประเภทข้อมูลไม่ถูกส่งให้โมเดล</p>
    <label className="field">เลือกหน้า เช่น 1, 3, 5-8<input className="input" aria-label="ช่วงหน้า PDF" value={selection} disabled={disabled || running} onChange={e => setSelection(e.target.value)} /></label>
    <div className="my-2 flex flex-wrap gap-2"><button className="button small" disabled={disabled || running} onClick={() => setSelection(`1-${pageCount}`)}>เลือกทุกหน้า</button><button className="button small" disabled={disabled || running} onClick={() => setSelection("")}>ล้างหน้า</button><span>เลือกแล้ว {pages.length} หน้า</span></div>
    <div className="mb-3 grid max-h-32 grid-cols-4 gap-2 overflow-auto">{Array.from({ length: pageCount }, (_, i) => i + 1).map(page => <label key={page} className="text-xs"><input type="checkbox" aria-label={`เลือกหน้า ${page}`} disabled={disabled || running} checked={pages.includes(page)} onChange={e => setSelection((e.target.checked ? [...pages, page] : pages.filter(p => p !== page)).sort((a,b) => a-b).join(", "))} /> หน้า {page}</label>)}</div>
    {invalid && <p role="alert" className="text-red-600">{invalid}</p>}
    <button className="button primary" disabled={disabled || running || !!invalid || !pages.length || !pipelines.length} onClick={() => void start(pages)}>ประมวลผลหน้าที่เลือก</button>
    {current && <p role="status">กำลังประมวลผลหน้า {current.page} ({rows.findIndex(r => r.page === current.page) + 1} / {rows.length} หน้าที่เลือก)</p>}
    <ul className="my-3 space-y-2" aria-live="polite">{rows.map(row => <li key={row.page}>หน้า {row.page} · {({ queued: "รอดำเนินการ", running: "กำลังประมวลผล", success: "สำเร็จ", error: "ผิดพลาด" } as Record<string,string>)[row.status ?? "queued"]} {row.test_case_id && <Link className="text-indigo-600 underline" href={`/test/${row.test_case_id}`}>เปิดผลและแก้ Ground Truth</Link>}</li>)}</ul>
    {!!failed.length && !running && <button className="button secondary" disabled={disabled} onClick={() => void start(failed)}>ลองหน้าที่ผิดพลาดใหม่ (สร้างชุดทดสอบใหม่)</button>}
    {error && <p role="alert" className="error-banner">{error}</p>}
  </section>;
}
