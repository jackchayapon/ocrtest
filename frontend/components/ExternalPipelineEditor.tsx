"use client";

import {useEffect, useState, type FormEvent} from "react";
import {getExternalOCRProviders, saveDynamicPipeline} from "@/lib/api";
import {managedProviders, saveManagedPipeline} from "@/lib/external-providers";
import type {ExternalOCRProvider, PipelineConfig} from "@/types";
import ManagedProviderForm from "./ManagedProviderForm";

export default function ExternalPipelineEditor({pipeline, onSaved, onCancel}: {
  pipeline?: PipelineConfig; onSaved: () => void; onCancel: () => void;
}) {
  const [mode, setMode] = useState(pipeline && !pipeline.external_provider?.provider_id.startsWith("managed_") ? "existing" : "managed");
  const [providers, setProviders] = useState<ExternalOCRProvider[]>([]);
  const [providerId, setProviderId] = useState(pipeline?.external_provider?.provider_id || "");
  const [name, setName] = useState(pipeline?.name || "");
  const [enabled, setEnabled] = useState(pipeline?.enabled ?? true);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const provider = providers.find(value => value.id === providerId);
  useEffect(() => {
    let active = true;
    Promise.all([getExternalOCRProviders(), managedProviders()]).then(([available, managed]) => {
      if (active) {setProviders([...available.filter(value => !managed.some(item => item.id === value.id)), ...managed]); setError("");}
    }).catch(error => {if (active) setError(error instanceof Error ? error.message : "โหลด Provider ไม่สำเร็จ");})
      .finally(() => {if (active) setLoading(false);});
    return () => {active = false;};
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
    } catch (error) {setError(error instanceof Error ? error.message : "บันทึกไม่สำเร็จ");}
    finally {setBusy(false);}
  }

  // Editing an environment provider creates an independent DB configuration.
  // Its server credential is never copied to a user-editable destination.
  const editableProvider = provider && !provider.managed ? {...provider, api_key_configured: false} : provider;
  return <div>
    <label className="field px-5 pt-5">การตั้งค่า External API<select className="select" value={mode} onChange={event => setMode(event.target.value)}>
      <option value="managed">กรอกหรือแก้ไข Endpoint และ API Key</option><option value="existing">เลือก Provider ที่บันทึกไว้</option>
    </select></label>
    {loading ? <p role="status" className="p-5">กำลังโหลด Provider…</p> : mode === "managed" ? <>
      {provider && !provider.managed && <p className="px-5 pt-4 text-sm">การแก้ Provider จาก Server จะสร้างสำเนาแยก ต้องตั้ง API Key ใหม่</p>}
      <ManagedProviderForm key={providerId} pipeline provider={editableProvider} initialName={pipeline?.name} initialEnabled={pipeline?.enabled}
        onCancel={onCancel} onSubmit={async (data, pipelineName, pipelineEnabled) => {
          await saveManagedPipeline({pipeline_id: pipeline?.pipeline_id,
            provider_id: provider?.managed ? provider.id : undefined,
            pipeline_name: pipelineName, pipeline_enabled: pipelineEnabled, provider: data});
          onSaved();
        }}/>
    </> : <form onSubmit={submit} className="space-y-4 p-5 sm:p-6">
      <fieldset disabled={busy} className="space-y-4 min-w-0">
        <label className="field">ชื่อ Pipeline<input className="input" required maxLength={100} value={name} onChange={e => setName(e.target.value)}/></label>
        <label className="field">External Provider<select className="select" required value={providerId} onChange={e => setProviderId(e.target.value)}>
          <option value="">เลือก Provider</option>{providers.map(value => <option key={value.id} value={value.id}>{value.name}{value.enabled === false ? " (ปิดใช้งาน)" : ""}</option>)}
        </select></label>
        {provider && <><p className="break-all text-sm">{provider.endpoint}</p><button type="button" className="button secondary" onClick={() => setMode("managed")}>แก้ไข Endpoint และ API Key</button></>}
        <label className="flex gap-2 text-sm"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)}/>เปิดใช้งานสำหรับทดสอบ OCR</label>
        <div className="flex justify-end gap-2"><button type="button" className="button secondary" onClick={onCancel}>ยกเลิก</button><button className="button primary" disabled={!provider} type="submit">{busy ? "กำลังบันทึก…" : "บันทึก Pipeline"}</button></div>
      </fieldset>
    </form>}
    {error && <p role="alert" className="error-banner">{error} <button type="button" className="underline" onClick={() => {setLoading(true); setRevision(value => value+1);}}>ลองใหม่</button></p>}
  </div>;
}
