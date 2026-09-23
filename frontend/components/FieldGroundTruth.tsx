"use client";
import { useState } from "react";
import * as api from "@/lib/api";
import type { FieldComparison, OCRField, PipelineRun } from "@/types";

const rate = (value: number | null | undefined) => value == null ? "—" : `${(value * 100).toFixed(2)}%`;
const names = { substitution: "อ่านผิด", insertion: "อ่านเกิน", deletion: "อ่านขาด" };

function FieldCard({ field, caseId, runId, selected, onSelect, onSaved, disabled }: {
  field: OCRField; caseId: string; runId: string; selected: boolean; onSelect: () => void; onSaved: () => Promise<void>; disabled: boolean;
}) {
  const [text, setText] = useState(field.ground_truth_raw ?? "");
  const [checked, setChecked] = useState<{ text: string; comparison: FieldComparison } | null>(field.evaluation ? { text: field.ground_truth_raw ?? "", comparison: field.evaluation } : null);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const comparison = checked?.text === text ? checked.comparison : null;
  async function act(confirm: boolean) {
    setBusy(true); setError("");
    try {
      if (confirm) { await api.saveFieldGT(caseId, runId, field.id, text, true); await onSaved(); }
      else setChecked({ text, comparison: await api.checkField(caseId, runId, field.id, text) });
    } catch (e) { setError(e instanceof Error ? e.message : "ตรวจข้อความไม่สำเร็จ"); }
    finally { setBusy(false); }
  }
  return <article className={`rounded-lg border p-3 mb-2 ${selected ? "border-indigo-500 bg-indigo-50/30" : "border-slate-200"}`} data-testid="ocr-field">
    <button className="mini-link" onClick={onSelect} aria-pressed={selected}>Field {String(field.field_index + 1).padStart(2, "0")}</button>
    <span className="float-right text-xs">Confidence {rate(field.confidence)}</span>
    <p className="my-2 whitespace-pre-wrap break-words"><strong>OCR:</strong> {field.ocr_text}</p>
    <details open={selected || undefined}>
      <summary className="cursor-pointer text-xs">ตรวจ Ground Truth {field.confirmed_at && text === field.ground_truth_raw ? "· ยืนยันแล้ว" : "· ยังไม่ยืนยัน"}</summary>
      <label className="block mt-2" htmlFor={`gt-field-${field.id}`}>GT Field {field.field_index + 1}</label>
      <textarea id={`gt-field-${field.id}`} className="input w-full" value={text} disabled={disabled || busy} onChange={e => setText(e.target.value)} />
      <div className="flex gap-2 mt-2">
        <button className="button small secondary" onClick={() => void act(false)} disabled={disabled || busy}>ตรวจ</button>
        <button className="button small primary" onClick={() => void act(true)} disabled={disabled || busy || !comparison}>ยืนยัน GT Field</button>
      </div>
      {error && <p role="alert" className="text-red-700">{error}</p>}
      {comparison && <div className="mt-2" aria-live="polite">
        <p className="text-xs">CER {rate(comparison.cer)} · WER {rate(comparison.wer)} · Exact Match {comparison.exact_match ? "ใช่" : "ไม่"}</p>
        <p className="whitespace-pre-wrap break-words mt-2" aria-label="ผลเปรียบเทียบ OCR">{comparison.spans.map((span, i) => span.kind === "equal" ? <span key={i}>{span.text}</span> : <span key={i} data-testid="field-error" data-error-type={span.kind} className="text-red-700 underline decoration-2" title={`${names[span.kind]}: GT ${span.missing ?? "∅"}`} aria-label={`${names[span.kind]} ${span.kind === "deletion" ? span.missing : span.text}`}>{span.kind === "deletion" ? `⟦ขาด: ${span.missing}⟧` : span.text}</span>)}</p>
        <p className="filter-note">ผลตรวจเป็น preview จนกด ยืนยัน GT Field · ขีดเส้นใต้สีแดง = อ่านผิด/เกิน; ⟦ขาด⟧ = อักขระที่ OCR ไม่ได้อ่าน</p>
      </div>}
    </details>
  </article>;
}

export default function FieldGroundTruth({ caseId, runs, selectedBoxId, onSelectBox, onSaved, disabled }: {
  caseId?: string; runs: PipelineRun[]; selectedBoxId: string | null; onSelectBox: (id: string) => void; onSaved: () => Promise<void>; disabled: boolean;
}) {
  return <section className="panel panel-body" aria-label="Ground Truth ราย Field">
    <h2>Ground Truth ราย Field</h2>
    <p className="filter-note">กรอบ OCR ของแต่ละ Pipeline แยกกัน · ตรวจเพื่อ preview และยืนยันทีละ Field · ไม่มีการจัดประเภทชื่อ/ที่อยู่</p>
    {!caseId || !runs.length ? <p className="empty-state">รัน OCR เพื่อแสดง Fields จากกรอบข้อความ</p> : runs.map(run => <div key={run.id} className="mb-4">
      <h3 className="font-semibold">{run.pipeline_name}</h3>
      {run.field_summary && <p className="text-xs my-2" data-testid="field-summary">ยืนยัน {run.field_summary.confirmed_fields}/{run.field_summary.total_fields} Fields · CER {rate(run.field_summary.cer)} · WER {rate(run.field_summary.wer)} · Exact Match {run.field_summary.exact_match == null ? "—" : run.field_summary.exact_match ? "ใช่" : "ไม่"}</p>}
      <div className="max-h-[480px] overflow-y-auto pr-1">{run.fields?.length ? run.fields.map(field => <FieldCard key={field.id} field={field} caseId={caseId} runId={run.id} selected={selectedBoxId === `${run.id}:${field.field_index}`} onSelect={() => onSelectBox(`${run.id}:${field.field_index}`)} onSaved={onSaved} disabled={disabled} />) : <p className="filter-note">ไม่มี Fields สำหรับผลนี้ · ใช้โหมดทั้งเอกสาร / ROI ได้</p>}</div>
      <p className="filter-note">สรุปเฉพาะ Fields ที่ยืนยัน: ผลรวมจำนวน edit ÷ ผลรวมหน่วย GT ไม่ใช่ค่าเฉลี่ยเปอร์เซ็นต์ · WER แบ่งคำด้วยช่องว่าง</p>
    </div>)}
  </section>;
}
