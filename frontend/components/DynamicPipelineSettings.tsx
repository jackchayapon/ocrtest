"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Cpu, Plus, Save, Settings2, X, Circle, PlugZap, Trash2 } from "lucide-react";
import { deletePipeline, getOCRModels, saveOCRModel, saveDynamicPipeline, testConnection } from "@/lib/api";
import {versionLabel, pipelineModelDisplay} from "@/lib/pipeline-model-label";
import type { DynamicPipelineInput, OCRModel, PipelineConfig } from "@/types";
import ExternalPipelineEditor from "@/components/ExternalPipelineEditor";

const messageOf = (e: unknown) => e instanceof Error ? e.message : "ไม่สามารถบันทึกได้ กรุณาลองอีกครั้ง";

function initial(p: PipelineConfig | undefined, models: OCRModel[]): DynamicPipelineInput {
  const selected = (kind: "det" | "rec") => {
    const existing = kind === "det" ? p?.det_model_id : p?.rec_model_id;
    if (existing) return existing;
    if (p?.execution_mode !== "integrated") return null;
    const version = p.source === "official" ? (kind === "det" ? "6" : "5") : p.integrated_options?.version;
    const weight = p.source === "official" ? "default" : (kind === "det" ? p.integrated_options?.det_weight : p.integrated_options?.rec_weight);
    return models.find(m => m.source === p.source && m.kind === kind && m.version === version && m.weight === weight)?.id || null;
  };
  const officialIntegrated = p?.source === "official";
  const det = p?.det_model || models.find(m => m.id === p?.det_model_id);
  const rec = p?.rec_model || models.find(m => m.id === p?.rec_model_id);
  const weight = (value?: string) => !value || value === "default" ? "baseline" : value;
  return { name: p?.name || "", source: p?.source === "external_api" ? "custom" : p?.source || "custom", execution_mode: officialIntegrated ? "integrated" : "det_rec",
    det_model_id: officialIntegrated ? null : selected("det"), rec_model_id: officialIntegrated ? null : selected("rec"),
    paddle_model_defaults: false,
    det_version: p?.integrated_options?.det_version || (det?.version.replace(/^v/, "") as "5" | "6") || "6", rec_version: p?.integrated_options?.rec_version || (rec?.version.replace(/^v/, "") as "5" | "6") || "5",
    version: p?.integrated_options?.version || "6", det_weight: p?.integrated_options?.det_weight || weight(det?.weight),
    rec_weight: p?.integrated_options?.rec_weight || weight(rec?.weight), enabled: p?.enabled ?? true };
}

function ModelPicker({ title, models, value, onChange }: {
  title: string; models: OCRModel[]; value: string | null; onChange: (id: string | null) => void;
}) {
  const selected = models.find(m => m.id === value);
  const [chosenVersion, setChosenVersion] = useState(selected?.version || "");
  const version = selected?.version || chosenVersion;
  const versions = [...new Set(models.map(m => m.version))].sort();
  return <fieldset className={`min-w-0 rounded-xl border p-5 space-y-4 ${models[0]?.kind === "rec" ? "border-violet-200 bg-violet-50/40" : "border-sky-200 bg-sky-50/50"}`}>
    <legend className="rounded-lg bg-white px-3 py-1 text-base font-semibold text-slate-900">{title}</legend>
    <p className="text-sm text-slate-600">{models[0]?.kind === "rec" ? "อ่านข้อความภายในกรอบที่ตรวจพบ" : "ค้นหาตำแหน่งและสร้างกรอบข้อความบนภาพ"}</p>
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="field">Model version
        <select className="select" required value={version} onChange={e => { setChosenVersion(e.target.value); onChange(null); }}>
          <option value="">เลือกเวอร์ชัน</option>{versions.map(v => <option key={v} value={v}>{versionLabel(v, models[0].kind, models[0].source)}</option>)}
        </select>
      </label>
      <label className="field">Weight / โมเดล
        <select className="select" required disabled={!version} value={value || ""} onChange={e => onChange(e.target.value || null)}>
          <option value="">เลือก weight</option>{models.filter(m => m.version === version).map(m => <option key={m.id} value={m.id}>{m.name} · {m.weight}</option>)}
        </select>
      </label>
    </div>
    {!models.length && <p className="text-sm text-amber-700">ยังไม่มีโมเดลในกลุ่มนี้ เพิ่มได้ที่ “จัดการโมเดล OCR”</p>}
    {selected && <details className="rounded-lg border border-slate-200 bg-white p-3 text-sm"><summary className="cursor-pointer text-slate-600">API ที่ใช้เรียกโมเดล</summary><code className="mt-2 block break-all text-slate-700">{selected.batch_path}</code></details>}
  </fieldset>;
}

function PipelineEditor({ pipeline, models, onSaved, onCancel }: {
  pipeline?: PipelineConfig; models: OCRModel[]; onSaved: () => void; onCancel: () => void;
}) {
  const [form, setForm] = useState(() => initial(pipeline, models));
  const [executionSource, setExecutionSource] = useState(pipeline?.execution_mode === "external_api" ? "external" : "internal");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  function change<K extends keyof DynamicPipelineInput>(key: K, value: DynamicPipelineInput[K]) {
    setForm(f => ({ ...f, [key]: value })); setError("");
  }
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try { await saveDynamicPipeline(form, pipeline?.pipeline_id); onSaved(); }
    catch (e) { setError(messageOf(e)); } finally { setBusy(false); }
  }
  const available = models.filter(m => m.source === form.source);
  function officialWeights(kind: "det" | "rec") {
    const weights = new Map(["baseline", "thai_ft_v1", "thai_ft_v2"].map(w => [w, w]));
    for (const model of available.filter(m => m.kind === kind && m.version.replace(/^v/, "") === form[`${kind}_version`] && m.weight !== "default")) {
      weights.set(model.weight, `${model.name} · ${model.weight}`);
    }
    const current = form[`${kind}_weight`];
    if (current && !weights.has(current)) weights.set(current, current);
    return [...weights];
  }
  const sourceSelector = <label className="field p-5 pb-0 sm:px-6">Pipeline execution source
    <select className="select" value={executionSource} disabled={busy} onChange={e => setExecutionSource(e.target.value)}>
      <option value="internal">โมเดลในระบบ (Custom / Official)</option><option value="external">External OCR API</option>
    </select>
  </label>;
  if (executionSource === "external") return <div>{sourceSelector}<ExternalPipelineEditor pipeline={pipeline} onSaved={onSaved} onCancel={onCancel}/></div>;
  return <div>{sourceSelector}<form onSubmit={submit} data-execution-mode={form.execution_mode} className="space-y-5 border-t border-slate-100 p-5 sm:p-6">
    <fieldset disabled={busy} className="space-y-5 min-w-0 [&_.field]:text-sm [&_.field]:text-slate-700 [&_.input]:bg-white [&_.select]:bg-white">
      <label className="flex flex-col gap-2"><span className="text-base font-semibold text-slate-900">ชื่อ Pipeline</span>
        <input className="input" required maxLength={100} placeholder="เช่น Custom V6 · Thai FT v2" value={form.name} onChange={e => change("name", e.target.value)} />
      </label>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-2"><span className="text-base font-semibold text-slate-900">1. ประเภทโมเดล</span>
          <select className="select" value={form.source} onChange={e => setForm(f => ({ ...f, source: e.target.value as DynamicPipelineInput["source"], execution_mode: e.target.value === "official" ? "integrated" : "det_rec", det_model_id: null, rec_model_id: null }))}>
            <option value="custom">Custom</option><option value="official">Official / Paddle</option>
          </select>
        </label>
      </div>
      {form.source === "official" && <p className="rounded-lg bg-sky-50 p-3 text-sm text-sky-900">เลือกเวอร์ชันและ weight ของ DET/REC แยกกันได้ ระบบส่งค่าทั้งหมดผ่าน PaddleOCR API เดียวด้วย engine=paddle</p>}
      {form.source === "official" && form.execution_mode === "integrated" ? <div className="space-y-4">
          {(["det", "rec"] as const).map(kind => <fieldset key={kind} className={`min-w-0 rounded-xl border p-5 space-y-4 ${kind === "det" ? "border-sky-200 bg-sky-50/50" : "border-violet-200 bg-violet-50/40"}`}>
            <legend className="rounded-lg bg-white px-3 py-1 text-base font-semibold text-slate-900">{kind === "det" ? "2. Text Detection" : "3. Text Recognition"}</legend>
            <p className="text-sm text-slate-600">{kind === "rec" ? "อ่านข้อความภายในกรอบที่ตรวจพบ" : "ค้นหาตำแหน่งและสร้างกรอบข้อความบนภาพ"}</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="field">Model version<select className="select" required value={form[`${kind}_version`] || ""} onChange={e => setForm(f => ({...f, [`${kind}_version`]: e.target.value, [`${kind}_weight`]: "baseline"}))}>
                <option value="">เลือกเวอร์ชัน</option>{["5", "6"].map(v => <option key={v} value={v}>{versionLabel(v, kind, "official")}</option>)}
              </select></label>
              <label className="field">Weight / โมเดล
                <select className="select" required disabled={!form[`${kind}_version`]} value={form[`${kind}_weight`]} onChange={e => change(`${kind}_weight`, e.target.value)}>
                  <option value="">เลือก weight</option>{officialWeights(kind).map(([weight, label]) => <option key={weight} value={weight}>{label}</option>)}
                </select>
              </label>
            </div>
          </fieldset>)}
          <p className="text-sm text-slate-600">เลือก DET/REC ข้ามรุ่นได้ ชื่อ variant ต้องตรงกับ model_variants.json และมี weights อยู่บน Gateway</p>
        <p className="break-all rounded-lg bg-slate-100 p-3 font-mono text-xs text-slate-700">
          /api/v1/ocr-results?engine=paddle{`&det_version=${form.det_version}&rec_version=${form.rec_version}&det_model=${encodeURIComponent(form.det_weight)}&rec_model=${encodeURIComponent(form.rec_weight)}`}
        </p>
      </div> : <div className="space-y-4">
        <ModelPicker key={`det-${form.source}`} title="2. Text Detection" models={available.filter(m => m.kind === "det")} value={form.det_model_id} onChange={id => change("det_model_id", id)} />
        <ModelPicker key={`rec-${form.source}`} title="3. Text Recognition" models={available.filter(m => m.kind === "rec")} value={form.rec_model_id} onChange={id => change("rec_model_id", id)} />
      </div>}
      {form.execution_mode !== "integrated" && <p className="rounded-lg bg-slate-100 p-3 text-sm text-slate-600">เปลี่ยนชื่อ Weight / โมเดลได้ใน “จัดการโมเดล OCR” ด้านล่าง → แก้ไข → ชื่อที่แสดง</p>}
      {pipeline && pipeline.execution_mode !== form.execution_mode && <p className="text-xs text-slate-500">การบันทึกจะเปลี่ยนวิธีเรียกโมเดลตามตัวเลือกด้านบนสำหรับการรันครั้งถัดไป</p>}
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.enabled} onChange={e => change("enabled", e.target.checked)} />เปิดใช้งานสำหรับทดสอบ OCR</label>
      {error && <p className="error-banner" role="alert">{error}</p>}
      <div className="flex justify-end gap-2">
        <button type="button" className="button secondary" onClick={onCancel}>ยกเลิก</button>
        <button type="submit" className="button primary"><Save size={15} />{busy ? "กำลังบันทึก…" : "บันทึก Pipeline"}</button>
      </div>
    </fieldset>
  </form></div>;
}

function DynamicCard({ pipeline, models, onSaved }: { pipeline: PipelineConfig; models: OCRModel[]; onSaved: () => void }) {
  const [confirmDelete,setConfirmDelete]=useState(false),[deleting,setDeleting]=useState(false),[deleteError,setDeleteError]=useState("");
  async function remove(){if(deleting)return;setDeleting(true);setDeleteError("");try{await deletePipeline(pipeline.pipeline_id);onSaved();}catch(e){setDeleteError(messageOf(e));}finally{setDeleting(false);}}
  const [editing, setEditing] = useState(false), [testing, setTesting] = useState(false), [message, setMessage] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const external = pipeline.execution_mode === "external_api";
  const ready = (status === "gateway_connected" || status === "provider_ready") && pipeline.enabled && !testing;
  const statusText = !pipeline.enabled ? "ปิดใช้งาน" : testing ? "กำลังทดสอบการเชื่อมต่อ…" : ready ? external ? "Provider รายงานพร้อม · ยังไม่ได้ทดสอบ OCR" : "พร้อมใช้งาน · Gateway" : status === "reachable" || status === "configuration_valid" ? "ตรวจบางส่วนแล้ว · ยังไม่ได้ทดสอบ OCR" : status ? "เชื่อมต่อไม่สำเร็จ" : "ยังไม่ได้ทดสอบการเชื่อมต่อ";
  function modelText(kind: "det" | "rec") {
    return pipelineModelDisplay(pipeline, kind).summary;
  }
  async function check() {
    setTesting(true); setMessage(""); setStatus(null);
    try { const result = await testConnection(pipeline.pipeline_id); setStatus(result.status); setMessage(result.message); }
    catch (e) { setStatus("unavailable"); setMessage(messageOf(e)); } finally { setTesting(false); }
  }
  return <section className="panel overflow-hidden">
    <div className="p-5 sm:p-6 flex flex-wrap justify-between gap-4 border-b border-slate-100">
      <div className="flex gap-3 min-w-0"><span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600"><Cpu size={23} /></span><div>
        <div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold break-words">{pipeline.name}</h3>
          <span role="status" className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-xs ${ready ? "bg-teal-50 text-teal-700" : "bg-slate-100 text-slate-500"}`}><Circle size={7} fill="currentColor" />{statusText}</span>
        </div>
        <p className="mt-1 text-xs text-slate-500">{pipeline.enabled ? "เปิดใช้งานสำหรับทดสอบ OCR" : "ปิดใช้งานสำหรับทดสอบ OCR"}</p>
      </div></div>
      <code className="self-start rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-400 break-all">{pipeline.pipeline_id}</code>
    </div>
    <div className="p-5 sm:p-6 space-y-4">
      <p className="text-sm">Engine pipeline <code className="ml-2 rounded bg-slate-100 px-2 py-1">{pipeline.source || "—"}</code></p>
      {external ? <p className="text-sm">External OCR API · {pipeline.external_provider?.provider_name || "Provider ไม่พร้อมใช้งาน"}</p> : <dl className="grid gap-4 sm:grid-cols-2 text-sm">
        <div><dt className="text-xs text-slate-500">โมเดล Text Detection</dt><dd className="mt-1 font-medium break-words">{modelText("det")}</dd></div>
        <div><dt className="text-xs text-slate-500">โมเดล Text Recognition</dt><dd className="mt-1 font-medium break-words">{modelText("rec")}</dd></div>
      </dl>}
      {message && <p role="status" className="text-sm text-slate-600">{message}</p>}
    </div>
    {editing && <PipelineEditor pipeline={pipeline} models={models} onSaved={() => { setEditing(false); setStatus(null); onSaved(); }} onCancel={() => setEditing(false)} />}
    <div className="flex flex-wrap justify-between items-center gap-3 border-t border-slate-100 bg-slate-50/40 px-5 py-4 sm:px-6">
      <p className="text-xs text-slate-500">สถานะการเชื่อมต่อ: {statusText}</p>
      <div className="flex flex-wrap gap-2"><button className="button secondary" disabled={deleting || confirmDelete || testing || editing || !pipeline.enabled} onClick={() => void check()}><PlugZap size={15} />{testing ? "กำลังทดสอบ…" : external ? "Test Connection" : "ทดสอบ Gateway"}</button>
        <button className="button secondary" disabled={testing || deleting || confirmDelete} onClick={() => setEditing(v => !v)}><Settings2 size={15} />{editing ? "ปิดการแก้ไข" : "แก้ไข"}</button>
        <button className="button secondary text-red-700" disabled={testing||editing||deleting} onClick={()=>{setConfirmDelete(true);setDeleteError("");}} aria-label={`ลบ Pipeline ${pipeline.name}`}><Trash2 size={15}/>ลบ</button></div>
    </div>
    {confirmDelete&&<div className="border-t bg-red-50 p-5 space-y-3"><p>ลบ Pipeline “{pipeline.name}” ออกจากรายการใช้งาน? ผล OCR และประวัติเดิมจะยังอยู่</p>{deleteError&&<p role="alert" className="error-banner">{deleteError}</p>}<div className="flex gap-2"><button className="button secondary" disabled={deleting} onClick={()=>setConfirmDelete(false)}>ยกเลิก</button><button className="button primary" disabled={deleting} onClick={()=>void remove()}>{deleting?"กำลังลบ…":"ยืนยันลบ Pipeline"}</button></div></div>}
  </section>;
}

function emptyModel(): Omit<OCRModel, "id"> {
  return { name: "", source: "custom", kind: "det", version: "6", weight: "baseline",
    single_path: "/api/v1/text-detections?version=6&model=baseline", batch_path: "/api/v1/text-detection-batches?version=6&model=baseline" };
}

function ModelRegistry({ models, onSaved }: { models: OCRModel[]; onSaved: () => void }) {
  const [kind, setKind] = useState<"det" | "rec">("det"), [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState(emptyModel), [busy, setBusy] = useState(false), [error, setError] = useState("");
  function edit(model?: OCRModel) {
    setError(""); setEditing(model?.id || "new");
    if (model) { const { id: _id, ...fields } = model; void _id; setForm(fields); }
    else { const fresh = emptyModel(); setForm({ ...fresh, kind, single_path: fresh.single_path.replace("detection", kind === "det" ? "detection" : "recognition"), batch_path: fresh.batch_path.replace("detection", kind === "det" ? "detection" : "recognition") }); }
  }
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try { await saveOCRModel(form, editing === "new" ? undefined : editing!); setEditing(null); onSaved(); }
    catch (e) { setError(messageOf(e)); } finally { setBusy(false); }
  }
  function pathChange(key: "single_path" | "batch_path", value: string) {
    const params = new URLSearchParams(value.split("?")[1] || "");
    setForm(f => ({ ...f, [key]: value, ...(key === "batch_path" ? {version: params.get("version") || f.version, weight: params.get("model") || params.get("weight") || "default"} : {}) }));
  }
  return <details className="panel border-sky-200 p-5 sm:p-6">
    <summary className="cursor-pointer font-semibold">จัดการโมเดล OCR · เพิ่ม / แก้ไข API Path</summary>
    <p className="mt-3 text-sm text-slate-600">เพิ่ม API สำหรับ Det/Rec หรือกดแก้ไขเพื่อเปลี่ยน “ชื่อที่แสดง” ชื่อใหม่จะใช้ในรายการเลือกโมเดล การเปลี่ยนชื่อไม่เปลี่ยน weight หรือ API ที่เรียก</p>
    <div className="my-4 flex flex-wrap gap-2">
      {(["det", "rec"] as const).map(k => <button key={k} className={`button ${kind === k ? "primary" : "secondary"}`} onClick={() => setKind(k)}>{k === "det" ? "Text Detection" : "Text Recognition"}</button>)}
      <button className="button secondary ml-auto" disabled={busy} onClick={() => edit()}><Plus size={15} />เพิ่มโมเดล</button>
    </div>
    {editing && <form onSubmit={submit} className="mb-5 rounded-xl border border-indigo-100 bg-slate-50 p-4 space-y-4">
      <fieldset disabled={busy} className="space-y-4">
        <h3 className="font-semibold">{editing === "new" ? "เพิ่ม" : "แก้ไข"}โมเดล {form.kind === "det" ? "Text Detection" : "Text Recognition"}</h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="field">ชื่อที่แสดง<input className="input" required maxLength={100} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} /></label>
          <label className="field">ประเภท<select className="select" value={form.source} onChange={e => setForm(f => ({ ...f, source: e.target.value as OCRModel["source"] }))}><option value="custom">Custom</option><option value="official">Official</option></select></label>
          <label className="field">Version<input className="input" required maxLength={50} value={form.version} onChange={e => setForm(f => ({ ...f, version: e.target.value }))} /></label>
          <label className="field">Weight<input className="input" required maxLength={100} value={form.weight} onChange={e => setForm(f => ({ ...f, weight: e.target.value }))} /></label>
        </div>
        <label className="field">Single API Path (ไม่บังคับ)<input className="input font-mono text-xs" maxLength={500} value={form.single_path} onChange={e => pathChange("single_path", e.target.value)} /></label>
        <label className="field">Batch API Path<input className="input font-mono text-xs" required maxLength={500} value={form.batch_path} onChange={e => pathChange("batch_path", e.target.value)} /></label>
        <p className="text-xs text-slate-500">ระบบเรียก Batch API และส่ง version/model ตาม path นี้ การแก้ไขมีผลกับการรันครั้งถัดไปของทุก Pipeline ที่ใช้โมเดลนี้</p>
        {error && <p className="error-banner" role="alert">{error}</p>}
        <div className="flex justify-end gap-2"><button type="button" className="button secondary" onClick={() => setEditing(null)}>ยกเลิก</button><button className="button primary" type="submit">{busy ? "กำลังบันทึก…" : "บันทึกโมเดล"}</button></div>
      </fieldset>
    </form>}
    <div className="grid gap-3 lg:grid-cols-2">{models.filter(m => m.kind === kind).map(m => <div key={m.id} className="rounded-xl border border-slate-200 bg-slate-50 p-4 flex items-center justify-between gap-4">
      <div className="min-w-0"><p className="font-medium text-sm">{m.name}</p><p className="text-xs text-slate-500">{m.source} · V{m.version} · {m.weight}</p><p className="mt-1 text-xs text-slate-400 break-all">{m.batch_path}</p></div>
      <button className="button secondary shrink-0" disabled={busy} onClick={() => edit(m)} aria-label={`แก้ไขโมเดล ${m.name}`}>แก้ไข</button>
    </div>)}</div>
  </details>;
}

export default function DynamicPipelineSettings({ pipelines, onChanged }: { pipelines: PipelineConfig[]; onChanged: () => void }) {
  const [models, setModels] = useState<OCRModel[]>([]), [creating, setCreating] = useState(false);
  const [error, setError] = useState(""), [loading, setLoading] = useState(true), [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    getOCRModels().then(data => { if (active) { setModels(data); setError(""); } }).catch(e => { if (active) setError(messageOf(e)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [revision]);
  return <div className="space-y-5">
    <section className="panel overflow-hidden">
      <div className="p-5 sm:p-6 flex flex-wrap items-center justify-between gap-4"><div><h2 className="font-semibold">Pipeline ของคุณ</h2><p className="text-sm text-slate-500 mt-1">ตั้งชื่อ เลือก Custom / Official แล้วปรับโมเดลและ weight ได้ตลอด</p></div>
        <button className="button primary" disabled={loading || !!error} onClick={() => setCreating(v => !v)}>{creating ? <X size={16} /> : <Plus size={16} />}{creating ? "ปิด" : "เพิ่ม Pipeline"}</button></div>
      {creating && <PipelineEditor models={models} onSaved={() => { setCreating(false); onChanged(); }} onCancel={() => setCreating(false)} />}
    </section>
    {error && <p className="error-banner" role="alert">{error} <button className="underline" onClick={() => setRevision(v => v + 1)}>ลองใหม่</button></p>}
    {loading ? <p role="status">กำลังโหลดโมเดล…</p> : !error && <>
      {pipelines.filter(p => p.execution_mode).map(p => <DynamicCard key={p.pipeline_id} pipeline={p} models={models} onSaved={onChanged} />)}
      <ModelRegistry models={models} onSaved={() => { setRevision(v => v + 1); onChanged(); }} />
    </>}
  </div>;
}
