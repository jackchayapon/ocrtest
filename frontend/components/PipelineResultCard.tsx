"use client";
import { messages, pipelineLabel, t, userError } from "@/lib/i18n/th";
import { Check, ChevronDown, Clock3 } from "lucide-react";
import type { PipelineConfig, PipelineRun } from "@/types";
import MetricBadge, { percent } from "./MetricBadge";
import { PIPELINE_COLORS } from "./PipelineSelector";

export default function PipelineResultCard({ pipeline, run, selectedBoxId, onSelectBox, running, staleMetrics }: { pipeline: PipelineConfig; run?: PipelineRun; selectedBoxId: string | null; onSelectBox: (id: string | null) => void; running?: boolean; staleMetrics?: boolean }) {
  const metrics = run?.metrics;
  return <article className={`result-card ${selectedBoxId?.startsWith(`${run?.id}:`) ? "selected" : ""}`} aria-label={messages.result(pipelineLabel(pipeline.pipeline_id, pipeline.name))}>
    <div className="result-title"><span className="pipeline-dot" style={{ background: PIPELINE_COLORS[pipeline.pipeline_id] }} />{pipelineLabel(pipeline.pipeline_id, pipeline.name)}{run?.status === "success" && <Check size={12} color="#67a68a" />}<span className="latency"><Clock3 size={10} />{run?.processing_time_ms != null ? `${run.processing_time_ms} ms` : "—"}</span></div>
    {running ? <p className="result-placeholder" role="status">{t("Running pipeline…")}</p> : !run ? <p className="result-placeholder">{t("Run a test to see the recognized text and metrics.")}</p> : run.status === "error" ? <div className="error-banner">{run.error_message ? userError(run.error_message) : t("This pipeline could not complete the test.")}</div> : <>
      <div className="result-text" data-testid={`result-text-${pipeline.pipeline_id}`}>{run.final_text ?? run.text ?? t("(empty output)")}</div>
      {!!run.boxes?.length && <div className="mt-2 flex flex-wrap gap-1.5">{run.boxes.map((box, index) => <button key={index} className={`button small ${selectedBoxId === `${run.id}:${index}` ? "active" : "ghost"}`} onClick={() => onSelectBox(selectedBoxId === `${run.id}:${index}` ? null : `${run.id}:${index}`)} aria-pressed={selectedBoxId === `${run.id}:${index}`} title={box.text}>{t("Box")} {index + 1}<span className="max-w-28 truncate text-[9px] font-normal">{box.text}</span></button>)}</div>}
      <div className="result-metrics"><MetricBadge label="CER ↓" value={percent(metrics?.cer)} good={metrics?.cer != null && metrics.cer < 0.05} /><MetricBadge label="WER ↓" value={percent(metrics?.wer)} good={metrics?.wer != null && metrics.wer < 0.05} /><MetricBadge label={t("EXACT MATCH")} value={metrics ? metrics.exact_match ? t("Yes") : t("No") : "—"} good={metrics?.exact_match} /><MetricBadge label={t("CONFIDENCE")} value={percent(run.confidence)} /></div>
      {!metrics && <p className="mt-2 text-[9px] text-slate-400">{t("Save ground truth to calculate accuracy.")}</p>}
      {staleMetrics && metrics && <p className="mt-2 text-[9px] text-amber-600">{t("Metrics use saved ground truth. Save your edits to recalculate.")}</p>}
      <details className="mt-3 border-t border-slate-100 pt-2"><summary className="flex cursor-pointer items-center gap-1 text-[9px] text-slate-400">{t("Raw OCR & metrics")}<ChevronDown size={10} /></summary><p className="mt-2 whitespace-pre-wrap break-words text-xs text-slate-500">{run.raw_text ?? t("No raw output provided.")}</p><div className="mt-2 text-[9px] text-slate-400">{t("Raw CER:")} {percent(run.raw_metrics?.cer)} · WER: {percent(run.raw_metrics?.wer)} {t("· Exact:")} {run.raw_metrics ? run.raw_metrics.exact_match ? t("Yes") : t("No") : "—"}</div></details>
    </>}
  </article>;
}
