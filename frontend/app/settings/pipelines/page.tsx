"use client";
import { pipelineLabel, statusLabel, t, userError } from "@/lib/i18n/th";

import { useEffect, useState, type FormEvent } from "react";
import { Check, CheckCircle2, Circle, Cpu, Globe2, Loader2, PlugZap, Save, Settings2, ShieldCheck } from "lucide-react";
import { getPipelines, testConnection, updatePipeline } from "@/lib/api";
import type { PipelineConfig } from "@/types";

function editable(config: PipelineConfig) {
  return {
    name: config.name,
    base_url: config.base_url || "",
    endpoint: config.endpoint || "",
    http_method: config.http_method,
    request_format: config.request_format,
    file_field_name: "image",
    enabled: config.enabled,
    engine: config.engine || "",
    include_roi: false,
  };
}

const DESCRIPTIONS: Record<string, string> = {
  mint: t("Custom OCR pipeline. Receives the selected crop, or the full image when no region is selected."),
  hutch_crop: t("Crop input strategy. Receives an image cropped to the selected test region."),
  hutch_full: t("เตรียมภาพเต็มพร้อม ROI โดยไม่ครอบภาพในแอป รอยืนยันรูปแบบ HTTP จาก Hutch"),
};

function PipelineCard({ pipeline }: { pipeline: PipelineConfig }) {
  const [saved, setSaved] = useState(pipeline);
  const [form, setForm] = useState(() => editable(pipeline));
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const dirty = JSON.stringify(form) !== JSON.stringify(editable(saved));
  const notConfigured = (!saved.base_url || !saved.endpoint);
  const status = !saved.enabled ? t("Disabled") : notConfigured ? t("Not configured") : (saved.last_connection_status ? statusLabel(saved.last_connection_status) : null) || t("Availability not checked");
  const badgeStyle = !saved.enabled ? "bg-slate-100 text-slate-500" : notConfigured ? "bg-amber-50 text-amber-700" : "bg-teal-50 text-teal-700";

  function change<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setMessage("");
    setError("");
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("save"); setError(""); setMessage("");
    try {
      const updated = await updatePipeline(saved.pipeline_id, { ...form, name: form.name.trim(), base_url: form.base_url.trim(), endpoint: form.endpoint.trim(), file_field_name: form.file_field_name.trim(), engine: form.engine.trim() || null });
      setSaved(updated); setForm(editable(updated)); setMessage(t("Pipeline settings saved."));
    } catch (cause) { setError(cause instanceof Error ? userError(cause.message) : t("Could not save this pipeline.")); }
    finally { setBusy(null); }
  }

  async function checkConnection() {
    if (dirty) return;
    setBusy("test"); setError(""); setMessage("");
    try {
      const result = await testConnection(saved.pipeline_id);
      setSaved((current) => ({ ...current, last_connection_status: result.status }));
      setMessage(statusLabel(result.status));
    } catch (cause) { setError(cause instanceof Error ? userError(cause.message) : t("Connection check failed.")); }
    finally { setBusy(null); }
  }

  return (
    <section className="panel overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 p-5 sm:p-6"><div className="flex items-start gap-3"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600"><Cpu size={20} /></span><div><div className="flex flex-wrap items-center gap-2"><h2 className="text-base font-semibold text-slate-800">{pipelineLabel(saved.pipeline_id, saved.name)}</h2><span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold ${badgeStyle}`}><Circle size={6} fill="currentColor" />{status}</span></div><p className="mt-1 max-w-xl text-xs leading-5 text-slate-500">{DESCRIPTIONS[saved.pipeline_id] || t("Configurable OCR pipeline adapter.")}</p></div></div><span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[10px] text-slate-400">{saved.pipeline_id}</span></div>
      <form onSubmit={save}>
        <fieldset disabled={busy !== null} className="min-w-0 border-0 p-5 sm:p-6">
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            <label className="field">{t("Display name")}<input className="input" required maxLength={100} value={form.name} onChange={(event) => change("name", event.target.value)} /></label>
            <label className="field">{t("Request format")}<select className="select" value={form.request_format} onChange={(event) => change("request_format", event.target.value as PipelineConfig["request_format"])}><option value="multipart">{t("Multipart form data")}</option><option value="json_base64">{t("JSON / Base64")}</option></select></label>
            <label className="field sm:col-span-2">{t("Base URL")}<input className="input font-mono text-xs" type="url" placeholder="https://your-ocr-service.example" autoComplete="off" value={form.base_url} onChange={(event) => change("base_url", event.target.value)} /><span className="text-[10px] font-normal text-slate-400">{t("ระบุที่อยู่ Gateway โดยไม่ใส่ข้อมูลลับ")}</span></label>
            <label className="field">{t("HTTP method")}<input className="input" value="POST" readOnly /></label>
            <label className="field">{t("Endpoint")}<input className="input font-mono text-xs" placeholder="/api/v1/ocr-results" autoComplete="off" value={form.endpoint} onChange={(event) => change("endpoint", event.target.value)} /></label>
            <label className="field">{t("Image field")}<input className="input font-mono text-xs" value="image" readOnly /></label>
            <label className="field">{t("Engine")}<input className="input font-mono text-xs" value={saved.pipeline_id === "mint" ? "custom" : "paddle"} readOnly /></label>
          </div>
          <div className="mt-5 flex flex-wrap gap-x-8 gap-y-4 rounded-lg bg-slate-50 p-4">
            <label className="flex cursor-pointer items-start gap-2.5"><input type="checkbox" className="mt-0.5 h-4 w-4 accent-indigo-600" checked={form.enabled} onChange={(event) => change("enabled", event.target.checked)} /><span><span className="block text-xs font-medium text-slate-700">{t("Pipeline enabled")}</span><span className="mt-1 block text-[10px] text-slate-500">{t("Available for benchmark runs")}</span></span></label>
            <div className="text-xs text-slate-500"><span className="block font-medium">{t("API Key configured:")} {saved.api_key_configured ? t("Yes") : t("No")}</span><span className="mt-1 block text-[10px]">{t("Mint และ Hutch Crop ส่ง PNG ที่ครอบแล้ว ส่วน Hutch Full รอยืนยันสัญญาการส่งภาพเต็มพร้อม ROI")}</span></div>
          </div>
          {!form.base_url.trim() && <p className="mt-4 flex items-start gap-2 text-xs leading-5 text-amber-700"><Globe2 size={15} className="mt-0.5 shrink-0" /><span>{t("กรุณาตั้งค่า Gateway URL ก่อนใช้งาน")}</span></p>}
          {saved.pipeline_id !== "mint" && <p className="mt-3 text-xs leading-5 text-slate-500">{t("Hutch request parameters are fixed for this benchmark: unclip ratio 1.7 · detection threshold 0.25 · box threshold 0.6.")}</p>}
          {error && <div className="error-banner mt-4" role="alert">{error}</div>}
          {message && <div className="mt-4 flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs leading-5 text-slate-600" role="status"><CheckCircle2 size={15} className="mt-0.5 shrink-0" />{message}</div>}
        </fieldset>
        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-slate-100 bg-slate-50/40 px-5 py-4 sm:px-6"><div><p className="text-[11px] text-slate-500">{t("Last connection:")} <span className="font-medium text-slate-700">{(saved.last_connection_status ? statusLabel(saved.last_connection_status) : null) || t("Not tested")}</span></p>{dirty && <p className="mt-1 text-[10px] text-amber-700">{t("Unsaved changes. Save before testing the connection.")}</p>}</div><div className="flex gap-2"><button type="button" className="button secondary" disabled={busy !== null || dirty} title={dirty ? t("Save your changes before testing") : t("Test the saved pipeline configuration")} onClick={checkConnection}>{busy === "test" ? <Loader2 size={14} className="animate-spin" /> : <PlugZap size={14} />} {t("Test connection")}</button><button className="button primary" type="submit" disabled={busy !== null || !dirty}>{busy === "save" ? <Loader2 size={14} className="animate-spin" /> : dirty ? <Save size={14} /> : <Check size={14} />}{busy === "save" ? t("Saving…") : dirty ? t("Save changes") : t("Saved")}</button></div></div>
      </form>
    </section>
  );
}

export default function PipelineSettingsPage() {
  const [pipelines, setPipelines] = useState<PipelineConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let active = true;
    async function fetchData() {
      setLoading(true); setError("");
      try { const result = await getPipelines(); if (active) setPipelines(result); }
      catch (cause) { if (active) setError(cause instanceof Error ? userError(cause.message) : t("Could not load pipeline settings.")); }
      finally { if (active) setLoading(false); }
    }
    void fetchData();
    return () => { active = false; };
  }, [revision]);

  return <div className="page-stack"><div className="page-heading"><div><p className="eyebrow">{t("WORKSPACE SETTINGS")}</p><h1>{t("Pipeline settings")}</h1><p className="muted">{t("Configure your OCR adapters and connect external services when they are ready.")}</p></div><span className="badge"><Settings2 size={13} /> {t("Provider configuration")}</span></div><div className="flex items-start gap-3 rounded-xl border border-indigo-100 bg-indigo-50/60 p-5"><ShieldCheck size={20} className="mt-0.5 shrink-0 text-indigo-500" /><div><p className="text-sm font-semibold text-indigo-900">{t("Connection settings here. Secrets on the server.")}</p><p className="mt-1 text-xs leading-6 text-indigo-800/80">{t("ตั้งค่า API Key ผ่าน environment ของ backend เท่านั้น ห้ามใส่รหัสลับใน URL หรือช่องตั้งค่านี้")}</p></div></div>{loading ? <div className="panel empty-state min-h-72"><Loader2 size={26} className="mx-auto mb-3 animate-spin text-indigo-500" /><p>{t("Loading pipeline settings…")}</p></div> : error ? <div className="error-banner" role="alert">{error} <button className="underline" onClick={() => setRevision((value) => value + 1)}>{t("Try again")}</button></div> : pipelines.length ? <div className="space-y-5">{pipelines.map((pipeline) => <PipelineCard key={pipeline.pipeline_id} pipeline={pipeline} />)}</div> : <div className="panel empty-state py-16"><Cpu size={30} className="mx-auto mb-4 text-indigo-300" /><h2 className="font-semibold text-slate-800">{t("No pipeline configurations found")}</h2><p className="mt-2 text-sm text-slate-500">{t("Initialize the backend database to create the three default pipeline adapters.")}</p><button className="button secondary mt-5" onClick={() => setRevision((value) => value + 1)}>{t("Reload settings")}</button></div>}</div>;
}
