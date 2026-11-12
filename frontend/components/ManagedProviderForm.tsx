"use client";
import {useState, type FormEvent} from "react";
import type {ExternalOCRProvider} from "@/types";
import type {ManagedProviderInput} from "@/lib/external-providers";

export function providerInput(provider?: ExternalOCRProvider): ManagedProviderInput {
  return {name: provider?.name || "", endpoint: provider?.endpoint || "", readiness_url: provider?.readiness_url || null,
    request_format: provider?.request_format || "multipart", image_field: provider?.image_field || "image",
    response_adapter: provider?.response_adapter || "openthai_v1", text_path: provider?.text_path || "text",
    confidence_path: provider?.confidence_path || null, auth_mode: provider?.auth_mode || "none",
    auth_header: provider?.auth_header || "X-API-Key", enabled: provider?.enabled ?? true,
    credential_action: provider?.auth_mode !== "none" && provider?.auth_mode && !provider.api_key_configured ? "replace" : "keep"};
}

export default function ManagedProviderForm({provider, initialName, initialEnabled = true, onSubmit, onCancel, pipeline = false}: {
  provider?: ExternalOCRProvider; initialName?: string; initialEnabled?: boolean;
  onSubmit: (data: ManagedProviderInput, name: string, enabled: boolean) => Promise<void>;
  onCancel: () => void; pipeline?: boolean;
}) {
  const [form, setForm] = useState(() => providerInput(provider));
  const [name, setName] = useState(initialName || "");
  const [pipelineEnabled, setPipelineEnabled] = useState(initialEnabled);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const originalOrigin = origin(provider?.endpoint);
  const changedOrigin = !!originalOrigin && origin(form.endpoint) !== originalOrigin;
  const canKeepKey = !!provider?.managed && !!provider.api_key_configured && !changedOrigin;
  function change<K extends keyof ManagedProviderInput>(field: K, value: ManagedProviderInput[K]) {setForm(current => ({...current, [field]: value}));}
  async function save(event: FormEvent) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError("");
    try {
      const data = {...form, ...(form.credential_action === "replace" ? {api_key: key} : {})};
      await onSubmit(data, name, pipelineEnabled); setKey("");
    } catch (error) {setError(error instanceof Error ? error.message : "บันทึกไม่สำเร็จ");}
    finally {setBusy(false); setKey("");}
  }
  return <form onSubmit={save} className="space-y-4 p-5 sm:p-6" aria-label={pipeline ? "ตั้งค่า External Pipeline" : "ตั้งค่า External Provider"}>
    <fieldset disabled={busy} className="space-y-4 min-w-0">
      {pipeline && <label className="field">ชื่อ Pipeline<input className="input" required maxLength={100} value={name} onChange={e => setName(e.target.value)}/></label>}
      <label className="field">ชื่อ Provider<input className="input" required maxLength={100} value={form.name} onChange={e => change("name", e.target.value)}/></label>
      <label className="field">API Endpoint URL<input className="input" type="url" required maxLength={500} value={form.endpoint} onChange={e => {
        const endpoint = e.target.value;
        setForm(current => ({...current, endpoint, credential_action: current.auth_mode !== "none" && origin(endpoint) !== originalOrigin ? "replace" : current.credential_action}));
        setKey("");
      }}/></label>
      {changedOrigin && provider?.api_key_configured && <p role="status" className="text-sm text-amber-800">Origin เปลี่ยนแล้ว ต้องใช้ API Key ใหม่ ระบบจะไม่ส่ง Key เดิมไปปลายทางใหม่</p>}
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="field">HTTP Method<input className="input" readOnly value="POST"/></label>
        <label className="field">Request Format<select className="select" value={form.request_format} onChange={e => change("request_format", e.target.value as ManagedProviderInput["request_format"])}><option value="multipart">Multipart/form-data</option><option value="json_base64">JSON Base64</option></select></label>
        <label className="field">Image Field Name<input className="input" required pattern="[A-Za-z][A-Za-z0-9_]{0,63}" value={form.image_field} onChange={e => change("image_field", e.target.value)}/></label>
        <label className="field">Response Adapter<select className="select" value={form.response_adapter} onChange={e => change("response_adapter", e.target.value as ManagedProviderInput["response_adapter"])}><option value="openthai_v1">OpenThai v1</option><option value="text_json">Generic Text JSON</option></select></label>
        {form.response_adapter === "text_json" && <>
          <label className="field">Text response path<input className="input" required maxLength={100} value={form.text_path} onChange={e => change("text_path", e.target.value)}/></label>
          <label className="field">Confidence response path (ไม่บังคับ)<input className="input" maxLength={100} value={form.confidence_path || ""} onChange={e => change("confidence_path", e.target.value || null)}/></label>
        </>}
      </div>
      <label className="field">Readiness URL (ไม่บังคับ)<input className="input" type="url" maxLength={500} value={form.readiness_url || ""} onChange={e => change("readiness_url", e.target.value || null)}/></label>
      <label className="flex items-center gap-2"><input type="checkbox" checked={form.auth_mode !== "none"} onChange={e => {change("auth_mode", e.target.checked ? "bearer" : "none"); change("credential_action", e.target.checked ? canKeepKey ? "keep" : "replace" : "remove"); setKey("");}}/>ใช้ API Key</label>
      {form.auth_mode !== "none" && <div className="grid gap-4 sm:grid-cols-2">
        <label className="field">Authentication type<select className="select" value={form.auth_mode} onChange={e => change("auth_mode", e.target.value as ManagedProviderInput["auth_mode"])}><option value="bearer">Bearer Token</option><option value="x_api_key">X-API-Key</option><option value="custom_header">Approved custom header</option></select></label>
        {form.auth_mode === "custom_header" && <label className="field">Header name<select className="select" value={form.auth_header} onChange={e => change("auth_header", e.target.value)}>{["X-API-Key", "X-Auth-Token", "Api-Key"].map(value => <option key={value}>{value}</option>)}</select></label>}
        <label className="field">จัดการ API Key<select className="select" value={form.credential_action} onChange={e => {change("credential_action", e.target.value as ManagedProviderInput["credential_action"]); setKey("");}}>
          {canKeepKey && <option value="keep">ใช้ Key เดิม</option>}<option value="replace">ตั้ง Key ใหม่</option><option value="remove">ลบ Key</option>
        </select></label>
        {form.credential_action === "replace" && <label className="field">API Key<input className="input" type="password" autoComplete="new-password" required maxLength={4096} value={key} onChange={e => setKey(e.target.value)}/></label>}
        {provider?.api_key_configured && <p className="text-sm text-slate-600">มี Key ที่บันทึกแล้ว</p>}
      </div>}
      <label className="flex gap-2"><input type="checkbox" checked={form.enabled} onChange={e => change("enabled", e.target.checked)}/>เปิดใช้งาน Provider</label>
      {pipeline && <label className="flex gap-2"><input type="checkbox" checked={pipelineEnabled} onChange={e => setPipelineEnabled(e.target.checked)}/>เปิดใช้งาน Pipeline</label>}
      <div className="flex flex-wrap justify-end gap-2"><button type="button" className="button secondary" onClick={onCancel}>ยกเลิก</button><button type="submit" className="button primary">{busy ? "กำลังบันทึก…" : pipeline ? "บันทึก Pipeline" : "บันทึก Provider"}</button></div>
    </fieldset>
    {error && <p role="alert" className="error-banner">{error}</p>}
  </form>;
}

function origin(value?: string) {
  try {return value ? new URL(value).origin : null;} catch {return null;}
}
