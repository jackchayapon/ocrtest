"use client";
import {useEffect, useState} from "react";
import {providerRequest, managedProviders, saveManagedProvider} from "@/lib/external-providers";
import type {ExternalOCRProvider} from "@/types";
import ManagedProviderForm from "./ManagedProviderForm";

export default function ManagedProviderRegistry({onChanged}: {onChanged: () => void}) {
  const [providers, setProviders] = useState<ExternalOCRProvider[]>([]);
  const [editing, setEditing] = useState<ExternalOCRProvider | null>(null);
  const [remove, setRemove] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    managedProviders().then(values => {if (active) {setProviders(values); setError("");}})
      .catch(error => {if (active) setError(error instanceof Error ? error.message : "โหลด Provider ไม่สำเร็จ");});
    return () => {active = false;};
  }, [revision]);
  return <section className="panel p-5 space-y-4" aria-label="จัดการ External Providers">
    <h2 className="font-semibold">External Providers ที่จัดการในระบบ</h2>
    {error && <p role="alert" className="error-banner">{error}</p>}
    {providers.map(provider => <div key={provider.id} className="rounded-lg border p-4 space-y-2">
      <p className="font-medium">{provider.name} · {provider.enabled ? "เปิดใช้งาน" : "ปิดใช้งาน"}</p>
      <p className="break-all text-sm">{provider.endpoint}</p>
      <p className="text-sm">{provider.response_adapter} · {provider.auth_mode === "none" ? "ไม่ใช้ API Key" : provider.api_key_configured ? "ตั้งค่า API Key แล้ว" : "ยังไม่มี API Key"}</p>
      <div className="flex flex-wrap gap-2"><button className="button secondary" disabled={busy} onClick={() => {setEditing(provider); setRemove(null);}}>แก้ไข Provider {provider.name}</button><button className="button secondary" disabled={busy} onClick={() => {setRemove(provider.id); setEditing(null);}}>ลบ Provider {provider.name}</button></div>
      {remove === provider.id && <div className="space-y-2"><p>ยืนยันลบ Provider “{provider.name}”? ต้องย้ายหรือลบ Pipeline ที่อ้างถึงก่อน</p><div className="flex gap-2"><button className="button secondary" disabled={busy} onClick={() => setRemove(null)}>ยกเลิกการลบ</button><button className="button primary" disabled={busy} onClick={async () => {
        setBusy(true); setError("");
        try {await providerRequest(`/external-providers/${provider.id}`, undefined, "DELETE"); setRemove(null); setRevision(value => value+1); onChanged();}
        catch (error) {setError(error instanceof Error ? error.message : "ลบไม่สำเร็จ");}
        finally {setBusy(false);}
      }}>ยืนยันลบ Provider</button></div></div>}
    </div>)}
    {editing && <ManagedProviderForm key={editing.id} provider={editing} onCancel={() => setEditing(null)} onSubmit={async data => {
      await saveManagedProvider(data, editing.id); setEditing(null); setRevision(value => value+1); onChanged();
    }}/>}
  </section>;
}
