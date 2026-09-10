"use client";
import { categoryLabel, pipelineLabel, t, userError } from "@/lib/i18n/th";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowDown, ArrowUpRight, ChartNoAxesCombined, Layers3, Loader2, RefreshCw, Tags } from "lucide-react";
import { getCategories, getCategoryAnalytics, getPipelines } from "@/lib/api";
import type { Category, CategoryAnalytics, PipelineConfig, QueryFilters } from "@/types";
import { percent } from "@/components/MatrixTable";

const COLORS: Record<string, string> = { mint: "bg-indigo-500", hutch_crop: "bg-teal-500", hutch_full: "bg-violet-500" };

export default function CategoryAnalyticsPage() {
  const [data, setData] = useState<CategoryAnalytics[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [pipelines, setPipelines] = useState<PipelineConfig[]>([]);
  const [filters, setFilters] = useState<QueryFilters>({});
  const [showUntested, setShowUntested] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const invalidDates = !!(filters.date_from && filters.date_to && filters.date_from > filters.date_to);

  useEffect(() => {
    let active = true;
    async function fetchData() {
      setLoading(true); setError("");
      if (invalidDates) { setLoading(false); return; }
      try {
        const [analytics, categoryList, pipelineList] = await Promise.all([getCategoryAnalytics(filters), getCategories(), getPipelines()]);
        if (active) { setData(analytics); setCategories(categoryList); setPipelines(pipelineList); }
      } catch (cause) { if (active) setError(cause instanceof Error ? userError(cause.message) : t("Could not load category analytics.")); }
      finally { if (active) setLoading(false); }
    }
    void fetchData();
    return () => { active = false; };
  }, [filters, revision, invalidDates]);

  const visible = data.filter((category) => showUntested || category.test_cases > 0);
  const measured = data.filter((category) => category.pipelines.some((pipeline) => pipeline.evaluated_runs > 0));
  const maxCer = Math.max(0.1, ...visible.flatMap((category) => category.pipelines.map((pipeline) => pipeline.cer ?? 0)));
  const scaleMax = Math.ceil(maxCer * 10) / 10;
  const setFilter = (key: keyof QueryFilters, value: string) => setFilters((current) => ({ ...current, [key]: value || undefined }));

  return (
    <div className="page-stack">
      <div className="page-heading"><div><p className="eyebrow">{t("LOOK CLOSER")}</p><h1>{t("Category analysis")}</h1><p className="muted">{t("Find where each pipeline excels, from Thai text to difficult document conditions.")}</p></div><button className="button secondary" onClick={() => setRevision((value) => value + 1)} disabled={loading}><RefreshCw size={15} className={loading ? "animate-spin" : ""} /> {t("Refresh")}</button></div>
      <div className="panel filters flex flex-wrap items-end gap-4 p-5">
        <label className="field min-w-44 flex-1">{t("Category")}<select className="select" value={filters.category || ""} onChange={(event) => setFilter("category", event.target.value)}><option value="">{t("All categories")}</option>{categories.map((category) => <option key={category.id} value={category.code}>{categoryLabel(category)}</option>)}</select></label>
        <label className="field min-w-44 flex-1">Pipeline<select className="select" value={filters.pipeline || ""} onChange={(event) => setFilter("pipeline", event.target.value)}><option value="">{t("All pipelines")}</option>{pipelines.map((pipeline) => <option key={pipeline.pipeline_id} value={pipeline.pipeline_id}>{pipelineLabel(pipeline.pipeline_id, pipeline.name)}</option>)}</select></label>
        <label className="field">{t("From")}<input className="input" type="date" value={filters.date_from || ""} onChange={(event) => setFilter("date_from", event.target.value)} /></label>
        <label className="field">{t("To")}<input className="input" type="date" min={filters.date_from} value={filters.date_to || ""} onChange={(event) => setFilter("date_to", event.target.value)} /></label>
        {Object.values(filters).some(Boolean) && <button className="button secondary" onClick={() => setFilters({})}>{t("Clear")}</button>}
      </div>
      {invalidDates && <div className="error-banner" role="alert">{t("The end date must be on or after the start date.")}</div>}
      {error && <div className="error-banner" role="alert">{error} <button className="underline" onClick={() => setRevision((value) => value + 1)}>{t("Try again")}</button></div>}
      {loading ? <div className="panel empty-state min-h-80"><Loader2 size={26} className="mx-auto mb-3 animate-spin text-indigo-500" /><p>{t("Loading category comparisons…")}</p></div> : !error && !invalidDates && <>
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="stat-card flex items-center gap-4"><span className="rounded-xl bg-indigo-50 p-3 text-indigo-500"><Tags size={21} /></span><div><p className="text-xs text-slate-500">{t("Categories in view")}</p><p className="mt-1 text-2xl font-semibold">{data.length}</p></div></div>
          <div className="stat-card flex items-center gap-4"><span className="rounded-xl bg-teal-50 p-3 text-teal-600"><ChartNoAxesCombined size={21} /></span><div><p className="text-xs text-slate-500">{t("With evaluated results")}</p><p className="mt-1 text-2xl font-semibold">{measured.length}</p></div></div>
          <div className="stat-card flex items-center gap-4"><span className="rounded-xl bg-violet-50 p-3 text-violet-500"><Layers3 size={21} /></span><div><p className="text-xs text-slate-500">{t("Category assignments")}</p><p className="mt-1 text-2xl font-semibold">{data.reduce((sum, category) => sum + category.test_cases, 0)}</p></div></div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-4"><div><h2 className="section-title">{t("Character error by category")}</h2><p className="mt-1 text-xs text-slate-500">{t("All bars share a scale of 0–")}{percent(scaleMax, 0)} {t("CER. Shorter is better.")}</p></div><label className="flex cursor-pointer items-center gap-2 text-xs text-slate-600"><input type="checkbox" className="h-4 w-4 accent-indigo-600" checked={showUntested} onChange={(event) => setShowUntested(event.target.checked)} /> {t("Show untested categories")}</label></div>
        <div className="flex flex-wrap gap-5 text-xs text-slate-500">{pipelines.filter((pipeline) => !filters.pipeline || filters.pipeline === pipeline.pipeline_id).map((pipeline) => <span className="flex items-center gap-2" key={pipeline.pipeline_id}><span className={`h-2 w-2 rounded-full ${COLORS[pipeline.pipeline_id] || "bg-slate-400"}`} />{pipelineLabel(pipeline.pipeline_id, pipeline.name)}</span>)}</div>
        {visible.length ? <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">{visible.map((category) => {
          const measuredRows = category.pipelines.filter((pipeline) => pipeline.cer != null);
          const bestCer = measuredRows.length ? Math.min(...measuredRows.map((pipeline) => pipeline.cer!)) : null;
          return <section className="panel overflow-hidden" key={category.code}><div className="flex items-start justify-between gap-2 border-b border-slate-100 p-5"><div><h3 className="text-sm font-semibold text-slate-800">{categoryLabel(category)}</h3><p className="mt-1 font-mono text-[10px] text-slate-400">{category.code}</p></div><span className="rounded-md bg-slate-100 px-2 py-1 text-[10px] font-medium text-slate-500">{category.test_cases} {t("test units")}</span></div><div className="space-y-5 p-5">{category.pipelines.map((pipeline) => <div key={pipeline.pipeline_id}><div className="mb-2 flex items-center justify-between gap-2"><span className="text-xs font-medium text-slate-600">{pipelineLabel(pipeline.pipeline_id, pipeline.pipeline_name)}</span><span className={`flex items-center gap-1 text-xs font-semibold tabular-nums ${pipeline.cer != null && pipeline.cer === bestCer ? "text-emerald-600" : "text-slate-700"}`}>{pipeline.cer != null && pipeline.cer === bestCer && measuredRows.length > 1 && <ArrowDown size={12} />}{percent(pipeline.cer)}</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100" role="img" aria-label={`${pipelineLabel(pipeline.pipeline_id, pipeline.pipeline_name)}: ${pipeline.cer == null ? t("no evaluated result") : `CER ${percent(pipeline.cer)}`}`}><div className={`h-full rounded-full transition-all duration-500 ${COLORS[pipeline.pipeline_id] || "bg-slate-400"}`} style={{ width: `${pipeline.cer == null ? 0 : pipeline.cer / scaleMax * 100}%` }} /></div><div className="mt-1.5 flex justify-between text-[10px] text-slate-400"><span>{pipeline.evaluated_runs} {t("evaluated units")}{pipeline.failed_runs ? ` · ${pipeline.failed_runs} ${t("failed units")}` : ""}</span><span>{pipeline.exact_match_rate == null ? t("Awaiting ground truth") : `${percent(pipeline.exact_match_rate, 0)} ${t("exact units")}`}</span></div></div>)}{!category.pipelines.length && <p className="py-5 text-center text-xs text-slate-400">{t("No pipeline results yet.")}</p>}</div><Link className="flex items-center justify-between border-t border-slate-100 bg-slate-50/60 px-5 py-3 text-[11px] font-medium text-indigo-600 hover:bg-indigo-50" href={`/?category=${encodeURIComponent(category.code)}`}>{t("Create a test in this category")} <ArrowUpRight size={13} /></Link></section>;
        })}</div> : <div className="panel empty-state py-16"><Tags size={30} className="mx-auto mb-4 text-indigo-300" /><h2 className="font-semibold text-slate-800">{t("No tagged tests in this view")}</h2><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">{t("Add categories to a test case and run your pipelines to compare performance by content type.")}</p><Link className="button primary mt-5" href="/">{t("Open testing workspace")} <ArrowUpRight size={14} /></Link></div>}
        <p className="text-xs leading-6 text-slate-500">{t("Categories are assigned manually, and one test can appear in multiple categories. Comparisons use each pipeline’s latest run per test. CER is the primary metric for Thai text; WER uses whitespace tokenization. Sample sizes can differ between pipelines, so compare evaluated counts alongside error rates.")}</p>
      </>}
    </div>
  );
}
