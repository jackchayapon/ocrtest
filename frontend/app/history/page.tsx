"use client";
import { categoryLabel, messages, pipelineLabel, statusLabel, t, userError } from "@/lib/i18n/th";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { ArrowRight, ChevronLeft, ChevronRight, Clock3, History, Loader2, Plus, RefreshCw, Search } from "lucide-react";
import { assetUrl, cropUrl, getCategories, getHistory, getPipelines } from "@/lib/api";
import type { Category, PipelineConfig, PipelineRun, QueryFilters, TestCase } from "@/types";
import { percent } from "@/components/MatrixTable";

const PAGE_SIZE = 20;
const PIPELINES = [{ id: "mint", name: t("Mint Custom") }, { id: "hutch_crop", name: "Hutch Crop" }, { id: "hutch_full", name: "Hutch Full" }];

function latestRuns(runs: PipelineRun[]) {
  const latest = new Map<string, PipelineRun>();
  for (const run of runs) {
    const current = latest.get(run.pipeline_id);
    if (!current || new Date(run.created_at).getTime() >= new Date(current.created_at).getTime()) latest.set(run.pipeline_id, run);
  }
  return latest;
}

function ResultCell({ run }: { run?: PipelineRun }) {
  if (!run) return <span className="text-xs text-slate-400">{t("Not run")}</span>;
  if (run.status === "error") return <div><span className="text-xs font-medium text-rose-600" title={run.error_message || t("Pipeline failed")}>{t("Failed")}</span></div>;
  return <div className="max-w-48"><p className="line-clamp-2 text-xs leading-5 text-slate-600" title={run.final_text ?? run.text ?? run.raw_text ?? ""}>{run.final_text ?? run.text ?? run.raw_text ?? t("(Empty result)")}</p><span className="mt-1.5 inline-block text-[10px] leading-relaxed text-slate-400">CER {percent(run.metrics?.cer)} · WER {percent(run.metrics?.wer)}<br />{t("Exact")} {run.metrics ? run.metrics.exact_match ? t("Yes") : t("No") : "—"} · {run.processing_time_ms ?? "—"} ms</span></div>;
}

export default function HistoryPage() {
  const [cases, setCases] = useState<TestCase[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [pipelines, setPipelines] = useState<PipelineConfig[]>([]);
  const [filters, setFilters] = useState<QueryFilters>({});
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [hasNextPage, setHasNextPage] = useState(false);
  const invalidDates = !!(filters.date_from && filters.date_to && filters.date_from > filters.date_to);

  useEffect(() => {
    let active = true;
    async function fetchData() {
      setLoading(true); setError("");
      if (invalidDates) { setLoading(false); return; }
      try {
        const [history, categoryList, pipelineList] = await Promise.all([getHistory({ ...filters, limit: PAGE_SIZE + 1, offset }), getCategories(), getPipelines()]);
        if (active) { setCases(history.slice(0, PAGE_SIZE)); setHasNextPage(history.length > PAGE_SIZE); setCategories(categoryList); setPipelines(pipelineList); }
      } catch (cause) { if (active) setError(cause instanceof Error ? userError(cause.message) : t("Could not load test history.")); }
      finally { if (active) setLoading(false); }
    }
    void fetchData();
    return () => { active = false; };
  }, [filters, offset, revision, invalidDates]);

  function setFilter(key: keyof QueryFilters, value: string) { setOffset(0); setFilters((current) => ({ ...current, [key]: value || undefined })); }

  return (
    <div className="page-stack">
      <div className="page-heading"><div><p className="eyebrow">{t("YOUR RESEARCH LOG")}</p><h1>{t("Test history")}</h1><p className="muted">{t("Revisit documents, review predictions, and continue where you left off.")}</p></div><div className="flex gap-2"><button className="button secondary" aria-label={t("Refresh history")} title={t("Refresh history")} disabled={loading} onClick={() => setRevision((value) => value + 1)}><RefreshCw size={16} className={loading ? "animate-spin" : ""} /></button><Link className="button primary" href="/"><Plus size={16} /> {t("New test")}</Link></div></div>

      <div className="panel filters flex flex-wrap items-end gap-4 p-5">
        <span className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-600"><Search size={16} /> {t("Filter tests")}</span>
        <label className="field min-w-44 flex-1">{t("Category")}<select className="select" value={filters.category || ""} onChange={(event) => setFilter("category", event.target.value)}><option value="">{t("All categories")}</option>{categories.map((category) => <option key={category.id} value={category.code}>{categoryLabel(category)}</option>)}</select></label>
        <label className="field min-w-44 flex-1">Pipeline<select className="select" value={filters.pipeline || ""} onChange={(event) => setFilter("pipeline", event.target.value)}><option value="">{t("All pipelines")}</option>{pipelines.map((pipeline) => <option key={pipeline.pipeline_id} value={pipeline.pipeline_id}>{pipelineLabel(pipeline.pipeline_id, pipeline.name)}</option>)}</select></label>
        <label className="field">{t("From")}<input className="input" type="date" value={filters.date_from || ""} onChange={(event) => setFilter("date_from", event.target.value)} /></label>
        <label className="field">{t("To")}<input className="input" type="date" min={filters.date_from} value={filters.date_to || ""} onChange={(event) => setFilter("date_to", event.target.value)} /></label>
        {Object.values(filters).some(Boolean) && <button className="button secondary" onClick={() => { setFilters({}); setOffset(0); }}>{t("Clear")}</button>}
      </div>
      {invalidDates && <div className="error-banner" role="alert">{t("The end date must be on or after the start date.")}</div>}
      {error && <div className="error-banner" role="alert">{error} <button className="underline" onClick={() => setRevision((value) => value + 1)}>{t("Try again")}</button></div>}
      {loading ? <div className="panel empty-state min-h-80"><Loader2 size={26} className="mx-auto mb-3 animate-spin text-indigo-500" /><p>{t("Loading test history…")}</p></div> : !error && !invalidDates && <section className="panel overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-5"><h2 className="section-title flex items-center gap-2"><History size={17} className="text-slate-400" /> {t("Saved test cases")}</h2><span className="text-xs text-slate-500">{t("Latest result for each pipeline")}</span></div>
        {cases.length ? <div className="table-wrap"><table className="data-table min-w-[1150px]"><caption className="sr-only">{t("Saved tests and their latest OCR results. Select a document to open the test.")}</caption><thead><tr><th scope="col">{t("Test / document")}</th><th scope="col">{t("Ground truth / categories")}</th>{PIPELINES.map((pipeline) => <th key={pipeline.id} scope="col">{pipeline.name}</th>)}<th scope="col">{t("Mean CER")}</th><th scope="col"><span className="sr-only">{t("Open test")}</span></th></tr></thead><tbody>{cases.map((testCase) => {
          const latest = latestRuns(testCase.runs);
          const measured = [...latest.values()].filter((run) => run.status === "success" && run.metrics?.cer != null);
          const avgCer = measured.length ? measured.reduce((sum, run) => sum + run.metrics!.cer!, 0) / measured.length : null;
          return <tr key={testCase.id}><td><Link href={`/test/${encodeURIComponent(testCase.id)}`} className="group flex items-start gap-3"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-400 group-hover:border-indigo-200 group-hover:text-indigo-500"><Image src={testCase.roi ? cropUrl(testCase.document_id, testCase.roi, testCase.page_number) : assetUrl(testCase.document.image_url)} alt={t("Test ROI preview")} width={38} height={38} unoptimized className="h-9 w-9 rounded object-contain" /></span><div className="max-w-52"><span className="block truncate text-sm font-semibold text-slate-800 group-hover:text-indigo-600" title={testCase.document.filename}>{testCase.document.filename}</span><span className="mt-1 block font-mono text-[10px] text-slate-400">#{testCase.id.slice(0, 8)}{testCase.page_number && <> · หน้า {testCase.page_number} / {testCase.document.page_count}</>}</span><span className="mt-2 flex items-center gap-1 text-[10px] text-slate-400"><Clock3 size={11} /><time dateTime={testCase.created_at}>{new Date(testCase.created_at).toLocaleDateString("th-TH", { year: "numeric", month: "short", day: "numeric" })}</time></span><span className={`mt-2 inline-block rounded px-1.5 py-0.5 text-[10px] font-medium capitalize ${testCase.status === "confirmed" ? "bg-emerald-50 text-emerald-700" : testCase.status === "tested" ? "bg-indigo-50 text-indigo-600" : "bg-slate-100 text-slate-500"}`}>{statusLabel(testCase.status)}</span></div></Link></td><td><p className="line-clamp-2 max-w-56 text-xs leading-5 text-slate-600" title={testCase.ground_truth_raw || ""}>{testCase.ground_truth_raw ?? <span className="italic text-slate-400">{t("No ground truth")}</span>}</p><div className="mt-2 flex max-w-56 flex-wrap gap-1">{testCase.categories.map((category) => <span className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-500" key={category.id}>{categoryLabel(category)}</span>)}</div></td>{PIPELINES.map((pipeline) => <td key={pipeline.id}><ResultCell run={latest.get(pipeline.id)} /></td>)}<td><span className={`text-sm font-semibold tabular-nums ${avgCer === 0 ? "text-emerald-600" : "text-slate-700"}`}>{percent(avgCer)}</span><span className="mt-1 block whitespace-nowrap text-[10px] text-slate-400">{measured.length ? messages.evaluated(measured.length) : t("Not evaluated")}</span></td><td><Link className="button secondary !p-2" href={`/test/${encodeURIComponent(testCase.id)}`} aria-label={messages.openTest(testCase.document.filename)}><ArrowRight size={15} /></Link></td></tr>;
        })}</tbody></table></div> : <div className="empty-state py-20"><History size={30} className="mx-auto mb-4 text-indigo-300" /><h2 className="font-semibold text-slate-800">{Object.values(filters).some(Boolean) ? t("No matching tests") : t("A fresh start for your research")}</h2><p className="mx-auto mt-2 max-w-md text-sm text-slate-500">{Object.values(filters).some(Boolean) ? t("Try a different category, pipeline, or date range.") : t("Your saved tests will appear here with their ground truth, categories, and pipeline results.")}</p><Link className="button primary mt-5" href="/"><Plus size={15} /> {t("Create a test case")}</Link></div>}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-5 py-4 text-xs text-slate-500"><span>{cases.length ? messages.showing(offset + 1, offset + cases.length) : t("0 test cases")} {t("· Mean CER uses evaluated latest results")}</span><div className="flex items-center gap-3"><button className="button secondary !px-2.5 !py-1.5" disabled={offset === 0} onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}><ChevronLeft size={14} /> {t("Previous")}</button><span>{t("Page")} {Math.floor(offset / PAGE_SIZE) + 1}</span><button className="button secondary !px-2.5 !py-1.5" disabled={!hasNextPage} onClick={() => setOffset((value) => value + PAGE_SIZE)}>{t("Next")} <ChevronRight size={14} /></button></div></div>
      </section>}
    </div>
  );
}
