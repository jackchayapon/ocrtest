"use client";

import {useEffect, useState, type FormEvent} from "react";
import {getExternalOCRProviders, saveDynamicPipeline, testConnection} from "@/lib/api";
import type {ExternalOCRProvider, PipelineConfig} from "@/types";

export default function ExternalPipelineEditor({pipeline, onSaved, onCancel}: {
  pipeline?: PipelineConfig; onSaved: () => void; onCancel: () => void;
}) {
  const [providers, setProviders] = useState<ExternalOCRProvider[]>([]);
  const [providerId, setProviderId] = useState(pipeline?.external_provider?.provider_id || "");
  const [name, setName] = useState(pipeline?.name || "");
  const [enabled, setEnabled] = useState(pipeline?.enabled ?? true);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [revision, setRevision] = useState(0);
  const provider = providers.find(value => value.id === providerId);
  useEffect(() => {
    let active = true;
    getExternalOCRProviders().then(values => { if (active) { setProviders(values); setError(""); } })
      .catch(error => { if (active) setError(error instanceof Error ? error.message : "โหลด Provider ไม่สำเร็จ"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [revision]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !provider) return;
    setBusy(true); setError("");
    try {
      await saveDynamicPipeline({name, enabled, provider_id: provider.id,
        source: "external_api", execution_mode: "external_api", det_model_id: null, rec_model_id: null,
        version: "6", det_weight: "baseline", rec_weight: "baseline"}, pipeline?.pipeline_id);
      onSaved();
    } catch (error) { setError(error instanceof Error ? error.message : "บันทึกไม่สำเร็จ"); }
    finally { setBusy(false); }
  }

  async function check() {
    if (!pipeline || busy) return;
    setBusy(true); setMessage(""); setError("");
    try { setMessage((await testConnection(pipeline.pipeline_id)).message); }
    catch (error) { setError(error instanceof Error ? error.message : "ตรวจการเชื่อมต่อไม่สำเร็จ"); }
    finally { setBusy(false); }
  }

  return <form onSubmit={submit} className="space-y-4 p-5 sm:p-6">
    <fieldset disabled={busy || loading} className="space-y-4 min-w-0">
      <label className="field">ชื่อ Pipeline<input className="input" required maxLength={100} value={name} onChange={e => setName(e.target.value)}/></label>
      <label className="field">Approved External Provider<select className="select" required value={providerId} onChange={e => {setProviderId(e.target.value); setMessage("");}}>
        <option value="">เลือก Provider</option>{providers.map(value => <option key={value.id} value={value.id}>{value.name}</option>)}
      </select></label>
      {provider && <div className="grid gap-4 sm:grid-cols-2">
        <label className="field sm:col-span-2">Endpoint URL<input className="input" readOnly value={provider.endpoint}/></label>
        <label className="field">HTTP method<input className="input" readOnly value={provider.http_method}/></label>
        <label className="field">Request format<input className="input" readOnly value={provider.request_format}/></label>
        <label className="field">Image field name<input className="input" readOnly value={provider.image_field}/></label>
        <label className="field">Response adapter<input className="input" readOnly value={provider.response_adapter}/></label>
        <label className="field">Authentication<input className="input" readOnly value={provider.auth_mode === "none" ? "ปิด" : provider.auth_mode}/></label>
        <p className="text-sm text-slate-600 self-end">{provider.auth_mode === "none" ? "Provider นี้เปิดให้เรียกโดยไม่ใช้ Key" : provider.api_key_configured ? "ตั้งค่า Credential บน Server แล้ว" : "ผู้ดูแลต้องตั้งค่า Credential บน Server"}</p>
      </div>}
      <p className="text-sm text-slate-600">ผู้ดูแลลงทะเบียน Endpoint, Adapter และ Credential ผ่าน configuration ฝั่ง Server แล้วจึงเลือกใช้งานที่นี่</p>
      <label className="flex gap-2 text-sm"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)}/>เปิดใช้งานสำหรับทดสอบ OCR</label>
      {message && <p role="status" className="text-sm">{message}</p>}
      <div className="flex flex-wrap justify-end gap-2">
        {pipeline && <button type="button" className="button secondary" onClick={() => void check()}>Test Connection ของค่าที่บันทึก</button>}
        <button type="button" className="button secondary" onClick={onCancel}>ยกเลิก</button>
        <button className="button primary" disabled={!provider} type="submit">{busy ? "กำลังบันทึก…" : "บันทึก Pipeline"}</button>
      </div>
    </fieldset>
    {loading && <p role="status">กำลังโหลด Provider…</p>}
    {!loading && !providers.length && !error && <p role="status">ยังไม่มี Provider ที่ผู้ดูแลอนุมัติ</p>}
    {error && <p role="alert" className="error-banner">{error} <button type="button" className="underline" onClick={() => {setLoading(true); setRevision(value => value+1);}}>ลองใหม่</button></p>}
  </form>;
}
