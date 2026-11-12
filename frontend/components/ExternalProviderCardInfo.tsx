"use client";
import {useEffect, useState} from "react";
import {getExternalOCRProviders} from "@/lib/api";
import type {ExternalOCRProvider} from "@/types";

export default function ExternalProviderCardInfo({id, fingerprint}: {id?: string; fingerprint?: string}) {
  const [provider, setProvider] = useState<ExternalOCRProvider | null>(null);
  useEffect(() => {
    let active = true;
    getExternalOCRProviders().then(values => {if (active) setProvider(Array.isArray(values) ? values.find(value => value.id === id) || null : null);})
      .catch(() => {if (active) setProvider(null);});
    return () => {active = false;};
  }, [id, fingerprint]);
  if (!provider) return <p className="text-sm text-slate-500">Provider ปิดใช้งานหรือยังไม่พร้อม</p>;
  return <dl className="grid gap-3 text-sm sm:grid-cols-2">
    <div className="sm:col-span-2"><dt className="text-slate-500">Endpoint</dt><dd className="break-all">{provider.endpoint}</dd></div>
    <div><dt className="text-slate-500">Response adapter</dt><dd>{provider.response_adapter}</dd></div>
    <div><dt className="text-slate-500">Authentication</dt><dd>{provider.auth_mode === "none" ? "ไม่ใช้ API Key" : provider.api_key_configured ? "ตั้งค่า API Key แล้ว" : "ยังไม่มี API Key"}</dd></div>
  </dl>;
}
