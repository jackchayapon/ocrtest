"use client";
import { categoryLabel, pipelineLabel, t, userError } from "@/lib/i18n/th";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowDownRight, BarChart3, CheckCheck, FlaskConical, Loader2, RefreshCw, SlidersHorizontal, Timer } from "lucide-react";
import { getCategories, getMatrix, getPipelines } from "@/lib/api";
import type { Category, MatrixRow, PipelineConfig, QueryFilters } from "@/types";
import MatrixTable, { percent } from "@/components/MatrixTable";

export default function MatrixPage() {
  const [rows, setRows] = useState<MatrixRow[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [pipelines, setPipelines] = useState<PipelineConfig[]>([]);
  const [filters, setFilters] = useState<QueryFilters>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const invalidDates = !!(filters.date_from && filters.date_to && filters.date_from > filters.date_to);

  useEffect(() => {
    let active = true;
    async function fetchData() {
      setLoading(true);
      setError("");
      if (invalidDates) { setLoading(false); return; }
      try {
        const [matrix, categoryList, pipelineList] = await Promise.all([getMatrix(filters), getCategories(), getPipelines()]);
        if (active) { setRows(matrix); setCategories(categoryList); setPipelines(pipelineList); }
      } catch (cause) {
        if (active) setError(cause instanceof Error ? userError(cause.message) : t("Could not load benchmark results."));
      } finally { if (active) setLoading(false); }
    }
    void fetchData();
    return () => { active = false; };
  }, [filters, revision, invalidDates]);

  const evaluated = rows.reduce((sum, row) => sum + row.evaluated_runs, 0);
  const measured = rows.filter((row) => row.cer != null);
  const best = measured.length ? measured.reduce((a, b) => a.cer! <= b.cer! ? a : b) : null;
  const timed = rows.filter((row) => row.avg_time_ms != null && row.successful_runs > 0);
  const timedRuns = timed.reduce((sum, row) => sum + row.successful_runs, 0);
  const avgTime = timedRuns ? timed.reduce((sum, row) => sum + row.avg_time_ms! * row.successful_runs, 0) / timedRuns : null;
  const setFilter = (key: keyof QueryFilters, value: string) => setFilters((current) => ({ ...current, [key]: value || undefined }));

  return (
    <div className="page-stack">
      <div className="page-heading"><div><p className="eyebrow">{t("MEASURE & COMPARE")}</p><h1>{t("Benchmark matrix")}</h1><p className="muted">{t("A clear view of how your OCR pipelines perform on the same test cases.")}</p></div><button className="button secondary" onClick={() => setRevision((value) => value + 1)} disabled={loading}><RefreshCw size={15} className={loading ? "animate-spin" : ""} /> {t("Refresh")}</button></div>

      <div className="panel filters flex flex-wrap items-end gap-4 p-5">
        <span className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-600"><SlidersHorizontal size={16} /> {t("Filters")}</span>
        <label className="field min-w-44 flex-1">{t("Category")}<select className="select" value={filters.category || ""} onChange={(event) => setFilter("category", event.target.value)}><option value="">{t("All categories")}</option>{categories.map((category) => <option key={category.id} value={category.code}>{categoryLabel(category)}</option>)}</select></label>
        <label className="field min-w-44 flex-1">Pipeline<select className="select" value={filters.pipeline || ""} onChange={(event) => setFilter("pipeline", event.target.value)}><option value="">{t("All pipelines")}</option>{pipelines.map((pipeline) => <option key={pipeline.pipeline_id} value={pipeline.pipeline_id}>{pipelineLabel(pipeline.pipeline_id, pipeline.name)}</option>)}</select></label>
        <label className="field">{t("From")}<input className="input" type="date" value={filters.date_from || ""} onChange={(event) => setFilter("date_from", event.target.value)} /></label>
        <label className="field">{t("To")}<input className="input" type="date" min={filters.date_from} value={filters.date_to || ""} onChange={(event) => setFilter("date_to", event.target.value)} /></label>
        <label className="field">{t("Document ID")}<input className="input" placeholder={t("Paste a document UUID")} defaultValue={filters.document || ""} key={filters.document || "empty"} onBlur={event => setFilter("document", event.target.value.trim())} /></label>
        {Object.values(filters).some(Boolean) && <button className="button secondary" onClick={() => setFilters({})}>{t("Clear")}</button>}
      </div>

      {invalidDates && <div className="error-banner" role="alert">{t("The end date must be on or after the start date.")}</div>}
      {error && <div className="error-banner" role="alert">{error} <button className="underline" onClick={() => setRevision((value) => value + 1)}>{t("Try again")}</button></div>}
      {loading ? <div className="panel empty-state min-h-80"><Loader2 className="mx-auto mb-3 animate-spin text-indigo-500" size={26} /><p>{t("Loading benchmark results…")}</p></div> : !error && !invalidDates && <>
        <div className="metric-grid grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <div className="stat-card"><span className="flex items-center justify-between text-xs font-medium text-slate-500">{t("PIPELINES WITH RESULTS")} <BarChart3 size={16} /></span><strong className="mt-4 block text-3xl font-semibold tracking-tight">{rows.filter((row) => row.tests > 0).length}<span className="ml-2 text-sm font-normal text-slate-400">/ {rows.length}</span></strong><p className="mt-2 text-xs text-slate-500">{t("Within selected filters")}</p></div>
          <div className="stat-card"><span className="flex items-center justify-between text-xs font-medium text-slate-500">{t("EVALUATED RESULTS")} <CheckCheck size={16} /></span><strong className="mt-4 block text-3xl font-semibold tracking-tight">{evaluated.toLocaleString()}</strong><p className="mt-2 text-xs text-slate-500">{t("Latest runs with ground truth")}</p></div>
          <div className="stat-card"><span className="flex items-center justify-between text-xs font-medium text-slate-500">{t("LOWEST CHARACTER ERROR")} <ArrowDownRight size={16} /></span><strong className="mt-4 block text-3xl font-semibold tracking-tight text-indigo-600">{percent(best?.cer)}</strong><p className="mt-2 text-xs text-slate-500">{best?.pipeline_name || t("Awaiting evaluated results")}</p></div>
          <div className="stat-card"><span className="flex items-center justify-between text-xs font-medium text-slate-500">{t("AVERAGE PROCESSING TIME")} <Timer size={16} /></span><strong className="mt-4 block text-3xl font-semibold tracking-tight">{avgTime == null ? "—" : Math.round(avgTime).toLocaleString()}<span className="ml-2 text-sm font-normal text-slate-400">{avgTime == null ? "" : "ms"}</span></strong><p className="mt-2 text-xs text-slate-500">{t("Across successful latest runs")}</p></div>
        </div>
        <section className="panel overflow-hidden"><div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-5"><div><h2 className="section-title">{t("Pipeline comparison")}</h2><p className="mt-1 text-xs text-slate-500">{t("Final OCR text compared with normalized ground truth")}</p></div><span className="badge">{t("CER is the primary metric")}</span></div><MatrixTable rows={rows} /></section>
        {!rows.some((row) => row.tests > 0) && <div className="panel empty-state py-10"><FlaskConical size={28} className="mx-auto mb-3 text-indigo-400" /><h2 className="font-semibold text-slate-800">{t("Your benchmark starts with a test")}</h2><p className="mx-auto mt-2 max-w-lg text-sm text-slate-500">{t("Upload a document, run the pipelines, and add ground truth to see measured comparisons here.")}</p><Link className="button primary mt-5" href="/">{t("Open testing workspace")}</Link></div>}
        <div className="rounded-xl border border-indigo-100 bg-indigo-50/60 px-5 py-4 text-xs leading-6 text-indigo-900"><strong>{t("Reading these results.")}</strong> {t("Lower CER and WER are better; higher exact match is better. CER compares Unicode characters and is the primary metric for Thai OCR. WER uses whitespace tokens, which do not represent semantic Thai word boundaries. Error rates can exceed 100% when predictions contain many insertions. Pipelines may have different evaluated sample counts.")}</div>
      </>}
    </div>
  );
}
