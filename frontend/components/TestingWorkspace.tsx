"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import Image from "next/image";
import { useEffect, useState } from "react";
import { ArrowUpRight, Crop, FileImage, FlaskConical, Info, Layers3, Loader2, ScanLine, Settings2, Sparkles, Tag, Wifi } from "lucide-react";
import * as api from "@/lib/api";
import type { AutoROISuggestion, Category, Document, GatewayStatus, PipelineConfig, PipelineRun, ROI, TestCase, ViewerBox } from "@/types";
import DocumentUploader from "@/components/DocumentUploader";
import GroundTruthEditor from "@/components/GroundTruthEditor";
import CategorySelector from "@/components/CategorySelector";
import PipelineSelector, { PIPELINE_COLORS } from "@/components/PipelineSelector";
import PipelineResultCard from "@/components/PipelineResultCard";
import TestToolbar from "@/components/TestToolbar";
import CropDebugPanel from "@/components/CropDebugPanel";
import { messages, statusLabel, t, userError } from "@/lib/i18n/th";

const DocumentViewer = dynamic(() => import("@/components/DocumentViewer"), { ssr: false, loading: () => <div className="empty-state">{t("Loading document viewer…")}</div> });

export default function TestingWorkspace({ initialTestCaseId }: { initialTestCaseId?: string }) {
  const [document, setDocument] = useState<Document | null>(null);
  const [testCase, setTestCase] = useState<TestCase | null>(null);
  const [roi, setRoi] = useState<ROI | null>(null);
  const [groundTruth, setGroundTruth] = useState("");
  const [gtTouched, setGtTouched] = useState(false);
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryCodes, setCategoryCodes] = useState<string[]>([]);
  const [pipelines, setPipelines] = useState<PipelineConfig[]>([]);
  const [selectedPipelines, setSelectedPipelines] = useState<string[]>([]);
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [selectedBoxId, setSelectedBoxId] = useState<string | null>(null);
  const [regionMode, setRegionMode] = useState(false);
  const [busy, setBusy] = useState<string | null>(t("Loading workspace"));
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [database, setDatabase] = useState<string>("");
  const [showBoxes, setShowBoxes] = useState(true);
  const [suggestions, setSuggestions] = useState<AutoROISuggestion[]>([]);
  const [autoMode, setAutoMode] = useState("text-line");
  const [gateway, setGateway] = useState<GatewayStatus | null>(null);
  const [maxUploadMB, setMaxUploadMB] = useState(20);

  useEffect(() => {
    let active = true;
    async function init() {
      try {
        const [configs, tags, health, uploadConfig] = await Promise.all([api.getPipelines(), api.getCategories(), api.getHealth(), api.getUploadConfig()]);
        if (!active) return;
        setMaxUploadMB(uploadConfig.max_upload_mb);
        setPipelines(configs); setSelectedPipelines(configs.filter(p => p.enabled).map(p => p.pipeline_id)); setCategories(tags);
        setDatabase(JSON.stringify(health).toLowerCase().includes("sqlite") ? t("Local development database") : t("PostgreSQL database"));
        const params = new URLSearchParams(window.location.search);
        const initialCategory = params.get("category");
        if (initialCategory && tags.some(tag => tag.code === initialCategory)) setCategoryCodes([initialCategory]);
        const id = initialTestCaseId ?? params.get("testCase");
        if (id) {
          const saved = await api.getTestCase(id);
          if (!active) return;
          setDocument(saved.document); setTestCase(saved); setRoi(saved.roi); setGroundTruth(saved.ground_truth_raw ?? ""); setGtTouched(saved.ground_truth_raw !== null); setCategoryCodes(saved.categories.map(c => c.code)); setRuns(saved.runs);
        }
      } catch (e) { if (active) setError(e instanceof Error ? userError(e.message) : t("Could not load the workspace.")); }
      finally { if (active) setBusy(null); }
    }
    void init();
    return () => { active = false; };
  }, [initialTestCaseId]);

  const dirtyGroundTruth = gtTouched && groundTruth !== testCase?.ground_truth_raw;
  const latestRuns = pipelines.map(p => [...runs].reverse().find(run => run.pipeline_id === p.pipeline_id)).filter((run): run is PipelineRun => !!run);
  const boxes: ViewerBox[] = latestRuns.filter(r => r.status === "success").flatMap(run => (run.boxes ?? []).map((box, index) => ({ ...box, id: `${run.id}:${index}`, pipelineId: run.pipeline_id, color: PIPELINE_COLORS[run.pipeline_id] ?? "#6256df" })));

  async function act(label: string, action: () => Promise<void>) {
    setBusy(label); setError(null); setNotice(null);
    try { await action(); } catch (e) { setError(e instanceof Error ? userError(e.message) : t("Something went wrong. Please try again.")); }
    finally { setBusy(null); }
  }

  function reset() {
    setDocument(null); setTestCase(null); setRoi(null); setGroundTruth(""); setGtTouched(false); setCategoryCodes([]); setRuns([]); setSelectedBoxId(null); setRegionMode(false); setNotice(null); setError(null); setSuggestions([]);
    window.history.replaceState(null, "", "/");
  }

  const upload = (file: File) => void act(t("Uploading document"), async () => {
    if (file.size > maxUploadMB * 1024 * 1024) throw new Error(t("File exceeds the upload limit"));
    if (!['application/pdf','image/png','image/jpeg','image/webp','image/tiff','image/bmp'].includes(file.type) && !(!file.type && /\.pdf$/i.test(file.name))) throw new Error(t("Unsupported file type"));
    const uploaded = await api.uploadDocument(file);
    reset(); setDocument(uploaded);
    setNotice(t("Document uploaded. Draw a test region or run the full page."));
  });

  const changePage = (page: number) => void act(t("Loading page"), async () => {
    if (!document || page === document.page_number) return;
    const next = await api.getDocumentPage(document.id, page);
    setDocument(next); setRoi(null); setTestCase(null); setRuns([]); setSelectedBoxId(null);
    setSuggestions([]); setGroundTruth(""); setGtTouched(false); setCategoryCodes([]); setRegionMode(false);
    window.history.replaceState(null, "", "/");
    setNotice(t("Page changed. Select a region and enter ground truth for this page. Saved tests remain in history."));
  });

  function changeRoi(next: ROI | null) {
    if (busy || JSON.stringify(roi) === JSON.stringify(next)) return;
    if (testCase) { setTestCase(null); setRuns([]); setSelectedBoxId(null); setNotice(t("Region changed. The next save creates a new test case; the previous case remains in history.")); window.history.replaceState(null, "", "/"); }
    setRoi(next);
  }

  async function ensureCase(): Promise<TestCase> {
    if (!document) throw new Error(t("Upload a document first."));
    let saved: TestCase;
    if (!testCase) {
      saved = await api.createTestCase({ document_id: document.id, page_number: document.page_number, roi, ground_truth_raw: gtTouched ? groundTruth : null, category_codes: categoryCodes });
    } else {
      saved = await api.updateTestCase(testCase.id, { category_codes: categoryCodes });
      if (gtTouched && saved.ground_truth_raw !== groundTruth) saved = await api.saveGroundTruth(saved.id, groundTruth);
    }
    setTestCase(saved); setRuns(saved.runs);
    window.history.replaceState(null, "", `/test/${saved.id}`);
    return saved;
  }

  const save = () => void act(t("Saving test case"), async () => { await ensureCase(); setNotice(t("Test case saved. You can reopen it from Test history.")); });
  const saveTruth = (confirmed: boolean) => void act(t("Saving ground truth"), async () => {
    const saved = await ensureCase();
    const updated = await api.saveGroundTruth(saved.id, groundTruth, confirmed);
    setGtTouched(true); setTestCase(updated); setRuns(updated.runs);
    setNotice(confirmed ? t("Ground truth confirmed. Raw and final OCR metrics have been recalculated.") : t("Ground truth saved. Raw and final OCR metrics have been recalculated."));
  });
  const run = (ids: string[]) => void act(t("Running pipelines"), async () => {
    const saved = await ensureCase();
    const response = await api.runPipelines(saved.id, ids);
    const updated = await api.getTestCase(saved.id);
    setTestCase(updated); setRuns(updated.runs); setSelectedBoxId(null);
    const failed = response.runs.filter(r => r.status === "error").length;
    setNotice(messages.completed(response.runs.length - failed, failed, gtTouched));
  });

  return <div>
    <div className="page-heading"><div><div className="eyebrow">{initialTestCaseId ? t("SAVED EXPERIMENT") : t("EXPERIMENT WORKSPACE")}</div><h1>{initialTestCaseId ? t("Test case detail") : t("OCR Testing & Benchmark")}</h1><p>{t("One document. Multiple pipelines. See how they measure up.")}</p></div><div className="workspace-actions"><span className="badge"><FlaskConical size={11} />{t("Pipeline workspace")}</span><Link href="/matrix" className="button secondary">{t("View matrix")}<ArrowUpRight size={13} /></Link></div></div>
    <TestToolbar onUpload={upload} onReset={reset} onRegion={() => setRegionMode(!regionMode)} onRun={() => run(selectedPipelines)} onRunAll={() => run(pipelines.filter(p => p.enabled).map(p => p.pipeline_id))} onSave={save} busy={busy} hasDocument={!!document} regionMode={regionMode} canRun={selectedPipelines.length > 0} canRunAll={pipelines.some(p => p.enabled)} />
    {error && <div className="error-banner mb-4" role="alert">{error}<button className="button small ghost ml-3" onClick={() => window.location.reload()}>{t("Reload workspace")}</button></div>}
    {notice && <div className="success-banner mb-4" role="status">{notice}</div>}
    {busy && <div className="notice-banner mb-4" role="status"><Loader2 size={13} className="busy-spinner" />{busy}…</div>}
    <div className="testing-grid"><div>
      <section className="panel preview-panel"><div className="panel-header"><h2><FileImage size={15} />{t("Document preview")}</h2><div className="document-info">{document ? <span className="max-w-40 truncate" title={document.filename}>{document.filename}</span> : t("NO DOCUMENT")}{document && <span className="badge neutral">{document.width} × {document.height}</span>}</div></div>
        {document?.document_type === "pdf" && <nav className="pdf-pages" aria-label={t("PDF page navigation")}><strong>{t("PDF document")} · {document.page_count} {t("pages")}</strong><button className="button small" aria-label={t("Previous page")} disabled={!!busy || document.page_number === 1} onClick={() => changePage(document.page_number! - 1)}>‹</button><span data-testid="pdf-page-indicator" aria-live="polite">{messages.page(document.page_number ?? 1, document.page_count)}</span><label>{t("Go to page")} <select aria-label={t("Select PDF page")} disabled={!!busy} value={document.page_number ?? 1} onChange={event => changePage(Number(event.target.value))}>{Array.from({ length: document.page_count }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1}</option>)}</select></label><button className="button small" aria-label={t("Next page")} disabled={!!busy || document.page_number === document.page_count} onClick={() => changePage(document.page_number! + 1)}>›</button><p>{t("Changing page clears unsaved ROI and text. Save your test first to keep it.")}</p></nav>}
        {document ? <div style={{ pointerEvents: busy ? "none" : undefined }}><DocumentViewer key={`${document.id}:${document.page_number ?? 0}`} imageUrl={api.assetUrl(document.image_url)} width={document.width} height={document.height} roi={roi} onRoiChange={changeRoi} boxes={showBoxes ? boxes : []} selectedBoxId={selectedBoxId} onSelectBox={setSelectedBoxId} regionMode={regionMode} onRegionModeChange={setRegionMode} suggestions={suggestions} onSelectSuggestion={suggestion => { changeRoi(suggestion.roi); setSuggestions([]); }} /></div> : <div className="preview-placeholder" onDragOver={e => { e.preventDefault(); }} onDrop={e => { e.preventDefault(); const file = e.dataTransfer.files[0]; if (file && !busy) upload(file); }}><div className="upload-illustration"><div className="fake-line" /><div className="fake-line" /><div className="fake-line" /><div className="fake-line" /><div className="fake-line" /><ScanLine /></div><h3>{t("A new perspective on your OCR")}</h3><p>{t("Drop a document here, select a region, and compare your recognition pipelines.")}</p><DocumentUploader onUpload={upload} disabled={!!busy} label={t("Choose a document")} primary /><span className="mt-3 text-[9px] text-slate-400">{t("Supported: PDF, PNG, JPG, JPEG")} · {maxUploadMB} MB</span><button className="mini-link mt-5" disabled={!!busy} onClick={() => void act(t("Loading sample"), async () => { const file = await api.loadSample(); const uploaded = await api.uploadDocument(file); reset(); setDocument(uploaded); setNotice(t("เปิดเอกสารตัวอย่างแล้ว เลือกพื้นที่และกรอกข้อความที่ถูกต้องก่อนทดสอบ")); })}>{t("Or try the sample document")} <ArrowUpRight size={11} /></button></div>}
        <div className="preview-footer"><span className="flex items-center gap-1.5"><Crop size={11} />{roi ? messages.region(roi.x2 - roi.x1, roi.y2 - roi.y1) : t("Full page · no region selected")}</span><label className="flex cursor-pointer items-center gap-1.5"><input type="checkbox" checked={showBoxes} onChange={e => setShowBoxes(e.target.checked)} />{t("Show OCR boxes")}</label></div>
      </section>
      {document && <div className="panel mt-4 p-3"><div className="flex flex-wrap items-center gap-2"><Sparkles size={14} className="text-cyan-600" /><strong className="mr-auto text-[11px]">{t("Auto ROI suggestions")}</strong><select className="select max-w-28 text-[10px]" aria-label={t("Auto ROI mode")} value={autoMode} disabled={!!busy} onChange={e => setAutoMode(e.target.value)}><option value="text-line">{t("Text lines")}</option><option value="layout">{t("Layout")}</option><option value="hybrid">{t("Hybrid")}</option></select><button className="button small secondary" disabled={!!busy} onClick={() => void act(t("Detecting suggested regions"), async () => { const result = await api.getAutoROIs(document.id, autoMode, document.page_number); setSuggestions(result.regions); setNotice(result.regions.length ? messages.suggestions(result.regions.length) : t("No regions suggested. You can draw a region manually.")); })}>{t("Auto Detect")}</button>{!!suggestions.length && <button className="button small ghost" onClick={() => setSuggestions([])}>{t("Dismiss")}</button>}</div><p className="mt-2 text-[9px] leading-relaxed text-slate-400">{t("Optional Gateway detection. Select a suggestion to use it; manual selection is always available.")}</p>{!!suggestions.length && <div className="mt-2 flex flex-wrap gap-1.5">{suggestions.map((suggestion, i) => <button className="button small" key={suggestion.id} onClick={() => { changeRoi(suggestion.roi); setSuggestions([]); }}>{t("Region")} {i + 1}{suggestion.score != null && ` · ${Math.round(suggestion.score * 100)}%`}</button>)}</div>}</div>}
      {document && roi && <div className="panel crop-preview"><Image src={api.cropUrl(document.id, roi, document.page_number)} alt={t("Selected test region crop")} width={130} height={55} unoptimized /><div><strong>{t("Selected test region")}</strong><p>({roi.x1}, {roi.y1}) → ({roi.x2}, {roi.y2}{t(") · original pixels")}</p><button className="mini-link" disabled={!!busy} onClick={() => changeRoi(null)}>{t("Use full page")}</button></div></div>}
      <div className="notice-banner mt-4"><Info size={14} /><span>{t("Each pipeline processes the same test case using its configured input strategy.")}</span></div>
      <div className="metric-explainer mt-3">{database && <span>{database} · </span>}{t("Original image coordinates are preserved at every zoom level.")}{testCase && <span className="block mt-1">{t("Test case")} <Link href={`/test/${testCase.id}`} className="text-violet-500">{testCase.id.slice(0, 8)}</Link> · {statusLabel(testCase.status)}</span>}</div>
      <div className="mt-3 flex flex-wrap items-center gap-2"><button className="button small ghost" disabled={!!busy} onClick={() => void act(t("Checking Gateway"), async () => { setGateway(await api.getGatewayStatus()); })}><Wifi size={12} />{t("Check Gateway status")}</button>{gateway && <span className="text-[10px] text-slate-400">{statusLabel(gateway.gateway)} · Mint: {statusLabel(gateway.mint)} · Hutch: {statusLabel(gateway.hutch_crop)} · Auto ROI: {statusLabel(gateway.auto_roi)}</span>}</div>
      <CropDebugPanel runs={latestRuns} />
    </div><div className="right-stack">
      <GroundTruthEditor value={groundTruth} onChange={value => { setGroundTruth(value); setGtTouched(true); }} onSave={() => saveTruth(false)} onConfirm={() => saveTruth(true)} disabled={!!busy} canSave={!!document} status={testCase?.status} dirty={dirtyGroundTruth} />
      <section className="panel"><div className="panel-header"><h2><Tag size={14} />{t("Content categories")}</h2><span className="text-[9px] text-slate-400">{t("Select multiple")}</span></div><div className="panel-body"><CategorySelector categories={categories} selected={categoryCodes} onChange={setCategoryCodes} disabled={!!busy} />{!categories.length && <p className="text-[10px] text-slate-400">{t("Categories load when the backend is connected.")}</p>}</div></section>
      <section className="results-section"><div className="results-heading"><h2 className="flex items-center gap-2"><Layers3 size={14} color="#8a879d" />{t("Pipeline comparison")}</h2><Link className="mini-link" href="/settings/pipelines"><Settings2 size={11} />{t("Configure")}</Link></div><PipelineSelector pipelines={pipelines} selected={selectedPipelines} onChange={setSelectedPipelines} disabled={!!busy} /><div className="mt-3">{pipelines.map(pipeline => <PipelineResultCard key={pipeline.pipeline_id} pipeline={pipeline} run={latestRuns.find(r => r.pipeline_id === pipeline.pipeline_id)} selectedBoxId={selectedBoxId} onSelectBox={setSelectedBoxId} running={busy === t("Running pipelines") && selectedPipelines.includes(pipeline.pipeline_id)} staleMetrics={dirtyGroundTruth} />)}</div><div className="metric-explainer">{t("CER & WER: lower is better. Exact match: higher is better.")}<br />{t("CER is the primary Thai OCR metric. WER uses whitespace tokens.")}</div></section>
    </div></div>
  </div>;
}
