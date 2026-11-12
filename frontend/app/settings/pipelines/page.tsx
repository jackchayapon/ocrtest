"use client";
import {PageHeader,LoadingState} from "@/components/ConsoleUI";
import {t,userError} from "@/lib/i18n/th";
import {useEffect,useState} from "react";
import {ShieldCheck} from "lucide-react";
import {getPipelines} from "@/lib/api";
import type {PipelineConfig} from "@/types";
import DynamicPipelineSettings from "@/components/DynamicPipelineSettings";

export default function PipelineSettingsPage() {
  const [pipelines, setPipelines] = useState<PipelineConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let active = true;
    async function fetchData() {
      setLoading(true);
      setError("");
      try {
        const result = await getPipelines();
        if (active) setPipelines(result);
      } catch (cause) {
        if (active)
          setError(
            cause instanceof Error
              ? userError(cause.message)
              : t("Could not load pipeline settings."),
          );
      } finally {
        if (active) setLoading(false);
      }
    }
    void fetchData();
    return () => {
      active = false;
    };
  }, [revision]);

  return (
    <div className="page-stack">
      <PageHeader
        title="ตั้งค่า Pipeline"
        description="เพิ่มและแก้ไข Pipeline เลือกโมเดล เวอร์ชัน และ weight สำหรับ OCR"
      />
      <div className="flex items-start gap-3 rounded-xl border border-indigo-100 bg-indigo-50/60 p-5">
        <ShieldCheck size={20} className="mt-0.5 shrink-0 text-indigo-500" />
        <div>
          <p className="text-sm font-semibold text-indigo-900">
            {t("Connection settings here. Secrets on the server.")}
          </p>
          <p className="mt-1 text-xs leading-6 text-indigo-800/80">
            {t(
              "External API ตั้งค่า Key ผ่านช่อง API Key ที่เข้ารหัสบน Server ได้ ส่วน Internal Models ใช้ environment ของ Backend ห้ามใส่ Key ใน URL ข้อมูลและการตั้งค่าทั้งหมดใช้ร่วมกันแบบสาธารณะ",
            )}
          </p>
        </div>
      </div>
      {loading ? (
        <LoadingState label={t("Loading pipeline settings…")} />
      ) : error ? (
        <div className="error-banner" role="alert">
          {error}{" "}
          <button
            className="underline"
            onClick={() => setRevision((value) => value + 1)}
          >
            {t("Try again")}
          </button>
        </div>
      ) : pipelines.length ? (
        <div className="space-y-5">
          <DynamicPipelineSettings pipelines={pipelines} onChanged={() => setRevision(v => v + 1)} />

        </div>
      ) : (
        <DynamicPipelineSettings pipelines={pipelines} onChanged={() => setRevision(v => v + 1)} />
      )}
    </div>
  );
}
