"use client";
import PdfBatchPanel from "@/components/PdfBatchPanel";

import dynamic from "next/dynamic";
import Link from "next/link";
import Image from "next/image";
import { useEffect, useState } from "react";
import { ArrowUpRight, FileImage, Loader2, Sparkles } from "lucide-react";
import * as api from "@/lib/api";
import type {
  AutoROISuggestion,
  Category,
  Document,
  PipelineConfig,
  PipelineRun,
  ROI,
  TestCase,
  ViewerBox,
} from "@/types";
import DocumentUploader from "@/components/DocumentUploader";
import GroundTruthEditor from "@/components/GroundTruthEditor";
import CategorySelector from "@/components/CategorySelector";
import PipelineSelector, {
  PIPELINE_COLORS,
} from "@/components/PipelineSelector";
import PipelineResultCard from "@/components/PipelineResultCard";
import { PageHeader, CaseStatus } from "@/components/ConsoleUI";
import CropDebugPanel from "@/components/CropDebugPanel";
import {
  messages,
  categoryLabel,
  pipelineLabel,
  t,
  userError,
} from "@/lib/i18n/th";

const DocumentViewer = dynamic(() => import("@/components/DocumentViewer"), {
  ssr: false,
  loading: () => (
    <div className="empty-state">{t("Loading document viewer…")}</div>
  ),
});

export default function TestingWorkspace({
  initialTestCaseId,
}: {
  initialTestCaseId?: string;
}) {
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
  const [inlineReview, setInlineReview] = useState(false);
  const [batchRunTarget, setBatchRunTarget] = useState<HTMLDivElement | null>(
    null,
  );
  const [testMode, setTestMode] = useState("single");
  const [resultTab, setResultTab] = useState(
    initialTestCaseId ? "mint" : "all",
  );
  const [suggestions, setSuggestions] = useState<AutoROISuggestion[]>([]);
  const [autoMode, setAutoMode] = useState("text-line");
  const [maxUploadMB, setMaxUploadMB] = useState(20);

  useEffect(() => {
    let active = true;
    async function init() {
      try {
        const [configs, tags, uploadConfig] = await Promise.all([
          api.getPipelines(),
          api.getCategories(),
          api.getUploadConfig(),
        ]);
        if (!active) return;
        setMaxUploadMB(uploadConfig.max_upload_mb);
        setPipelines(configs);
        setSelectedPipelines(
          configs.filter((p) => p.enabled).map((p) => p.pipeline_id),
        );
        setCategories(tags);
        const params = new URLSearchParams(window.location.search);
        const initialCategory = params.get("category");
        if (initialCategory && tags.some((tag) => tag.code === initialCategory))
          setCategoryCodes([initialCategory]);
        const id = initialTestCaseId ?? params.get("testCase");
        if (id) {
          const saved = await api.getTestCase(id);
          if (!active) return;
          setDocument(saved.document);
          setTestCase(saved);
          setRoi(saved.roi);
          setGroundTruth(saved.ground_truth_raw ?? "");
          setGtTouched(saved.ground_truth_raw !== null);
          setCategoryCodes(saved.categories.map((c) => c.code));
          setRuns(saved.runs);
        }
      } catch (e) {
        if (active)
          setError(
            e instanceof Error
              ? userError(e.message)
              : t("Could not load the workspace."),
          );
      } finally {
        if (active) setBusy(null);
      }
    }
    void init();
    return () => {
      active = false;
    };
  }, [initialTestCaseId]);

  const dirtyGroundTruth =
    gtTouched && groundTruth !== testCase?.ground_truth_raw;
  const latestRuns = pipelines
    .map((p) =>
      [...runs].reverse().find((run) => run.pipeline_id === p.pipeline_id),
    )
    .filter((run): run is PipelineRun => !!run);
  const boxes: ViewerBox[] = latestRuns
    .filter((r) => r.status === "success")
    .flatMap((run) =>
      (run.boxes ?? []).map((box, index) => ({
        ...box,
        id: `${run.id}:${index}`,
        pipelineId: run.pipeline_id,
        color: PIPELINE_COLORS[run.pipeline_id] ?? "#6256df",
      })),
    );

  async function act(label: string, action: () => Promise<void>) {
    setBusy(label);
    setError(null);
    setNotice(null);
    try {
      await action();
    } catch (e) {
      setError(
        e instanceof Error
          ? userError(e.message)
          : t("Something went wrong. Please try again."),
      );
    } finally {
      setBusy(null);
    }
  }

  function reset() {
    setInlineReview(false);
    setTestMode("single");
    setResultTab("all");
    setDocument(null);
    setTestCase(null);
    setRoi(null);
    setGroundTruth("");
    setGtTouched(false);
    setCategoryCodes([]);
    setRuns([]);
    setSelectedBoxId(null);
    setRegionMode(false);
    setNotice(null);
    setError(null);
    setSuggestions([]);
    window.history.replaceState(null, "", "/");
  }

  const upload = (file: File) =>
    void act(t("Uploading document"), async () => {
      if (file.size > maxUploadMB * 1024 * 1024)
        throw new Error(t("File exceeds the upload limit"));
      if (
        ![
          "application/pdf",
          "image/png",
          "image/jpeg",
          "image/webp",
          "image/tiff",
          "image/bmp",
        ].includes(file.type) &&
        !(!file.type && /\.pdf$/i.test(file.name))
      )
        throw new Error(t("Unsupported file type"));
      const uploaded = await api.uploadDocument(file);
      reset();
      setDocument(uploaded);
      setNotice(
        t("Document uploaded. Draw a test region or run the full page."),
      );
    });

  const changePage = (page: number) =>
    void act(t("Loading page"), async () => {
      if (!document || page === document.page_number) return;
      const next = await api.getDocumentPage(document.id, page);
      setInlineReview(false);
      setDocument(next);
      setRoi(null);
      setTestCase(null);
      setRuns([]);
      setSelectedBoxId(null);
      setSuggestions([]);
      setGroundTruth("");
      setGtTouched(false);
      if (testMode === "single") setCategoryCodes([]);
      setRegionMode(false);
      window.history.replaceState(null, "", "/");
      setNotice(
        t(
          "Page changed. Select a region and enter ground truth for this page. Saved tests remain in history.",
        ),
      );
    });

  function changeRoi(next: ROI | null) {
    if (busy || JSON.stringify(roi) === JSON.stringify(next)) return;
    if (testCase) {
      setTestCase(null);
      setRuns([]);
      setSelectedBoxId(null);
      setNotice(
        t(
          "Region changed. The next save creates a new test case; the previous case remains in history.",
        ),
      );
      window.history.replaceState(null, "", "/");
    }
    setRoi(next);
  }

  async function ensureCase(): Promise<TestCase> {
    if (!document) throw new Error(t("Upload a document first."));
    let saved: TestCase;
    if (!testCase) {
      saved = await api.createTestCase({
        document_id: document.id,
        page_number: document.page_number,
        roi,
        ground_truth_raw: gtTouched ? groundTruth : null,
        category_codes: categoryCodes,
      });
    } else {
      saved = await api.updateTestCase(testCase.id, {
        category_codes: categoryCodes,
      });
      if (gtTouched && saved.ground_truth_raw !== groundTruth)
        saved = await api.saveGroundTruth(saved.id, groundTruth);
    }
    setTestCase(saved);
    setRuns(saved.runs);
    window.history.replaceState(null, "", `/test/${saved.id}`);
    return saved;
  }

  const save = () =>
    void act(t("Saving test case"), async () => {
      await ensureCase();
      setNotice(t("Test case saved. You can reopen it from Test history."));
    });
  const saveTruth = (confirmed: boolean) =>
    void act(t("Saving ground truth"), async () => {
      const saved =
        testMode === "batch" && inlineReview && testCase
          ? testCase
          : await ensureCase();
      const updated = await api.saveGroundTruth(
        saved.id,
        groundTruth,
        confirmed,
      );
      setGtTouched(true);
      setTestCase(updated);
      setRuns(updated.runs);
      setNotice(
        confirmed
          ? t(
              "Ground truth confirmed. Raw and final OCR metrics have been recalculated.",
            )
          : t(
              "Ground truth saved. Raw and final OCR metrics have been recalculated.",
            ),
      );
    });
  const run = (ids: string[]) =>
    void act(t("Running pipelines"), async () => {
      const saved = await ensureCase();
      const response = await api.runPipelines(saved.id, ids);
      const updated = await api.getTestCase(saved.id);
      setTestCase(updated);
      setRuns(updated.runs);
      setSelectedBoxId(null);
      const failed = response.runs.filter((r) => r.status === "error").length;
      setNotice(
        messages.completed(response.runs.length - failed, failed, gtTouched),
      );
    });

  const reviewBatchPage = (id: string) =>
    void act("กำลังเปิดผลรายหน้า", async () => {
      const saved = await api.getTestCase(id);
      setDocument(saved.document);
      setTestCase(saved);
      setRoi(null);
      setRuns(saved.runs);
      setGroundTruth(saved.ground_truth_raw ?? "");
      setGtTouched(saved.ground_truth_raw !== null);
      setSelectedBoxId(null);
      setRegionMode(false);
      setSuggestions([]);
      setResultTab("mint");
      setInlineReview(true);
      requestAnimationFrame(() =>
        window.document
          .getElementById("document-review")
          ?.scrollIntoView({ block: "start" }),
      );
    });
  function chooseMode(mode: string) {
    if (mode === testMode) return;
    setTestMode(mode);
    setInlineReview(false);
    setTestCase(null);
    setRuns([]);
    setRoi(null);
    setGroundTruth("");
    setGtTouched(false);
    setSelectedBoxId(null);
    setRegionMode(false);
    setSuggestions([]);
  }
  const detailMode = !!initialTestCaseId && !!testCase;
  const visiblePipelines = pipelines.filter(
    (p) => resultTab === "all" || resultTab === p.pipeline_id,
  );
  return (
    <div className="page-stack">
      <PageHeader
        title={
          detailMode ? t("Test case detail") : t("OCR Testing & Benchmark")
        }
        description={
          detailMode
            ? "ตรวจสอบเอกสาร ผลแต่ละ Pipeline และข้อความอ้างอิงของชุดทดสอบนี้"
            : "เลือกเอกสาร กำหนดพื้นที่ แล้วเปรียบเทียบผล OCR ในที่เดียว"
        }
        back={
          detailMode ? { href: "/history", label: "กลับไปประวัติ" } : undefined
        }
        actions={
          document ? (
            <>
              <Link className="button secondary" href="/history">
                ประวัติ
              </Link>
              {detailMode ? (
                <Link
                  className="button secondary"
                  href={`/logs?test_case_id=${testCase!.id}`}
                >
                  ดู Log ของการทดสอบนี้
                </Link>
              ) : (
                <DocumentUploader
                  onUpload={upload}
                  disabled={!!busy}
                  label="เปลี่ยนเอกสาร"
                />
              )}
            </>
          ) : undefined
        }
      />
      {error && (
        <div className="error-banner" role="alert">
          {error}{" "}
          <button
            className="button small ghost"
            onClick={() => window.location.reload()}
          >
            ลองโหลดใหม่
          </button>
        </div>
      )}
      {notice && (
        <div className="success-banner" role="status">
          {notice}
        </div>
      )}
      {busy && (
        <div className="notice-banner" role="status">
          <Loader2 size={15} className="busy-spinner" /> {busy}…
        </div>
      )}
      {!document ? (
        <section className="panel upload-first">
          <div
            className="upload-drop"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const file = e.dataTransfer.files[0];
              if (file && !busy) upload(file);
            }}
          >
            <FileImage size={38} />
            <h2>เริ่มทดสอบจากเอกสารของคุณ</h2>
            <p>
              อัปโหลดภาพหรือ PDF เพื่อเลือกหน้า วาดพื้นที่ทดสอบ และตรวจผลจาก 3
              Pipeline
            </p>
            <DocumentUploader
              onUpload={upload}
              disabled={!!busy}
              label={t("Upload document")}
              primary
            />
            <span className="muted">
              PDF, PNG, JPG · สูงสุด {maxUploadMB} MB
            </span>
            <button
              className="mini-link"
              disabled={!!busy}
              onClick={() =>
                void act(t("Loading sample"), async () => {
                  const file = await api.loadSample();
                  const uploaded = await api.uploadDocument(file);
                  reset();
                  setDocument(uploaded);
                })
              }
            >
              {t("Or try the sample document")} <ArrowUpRight size={14} />
            </button>
          </div>
          <div className="upload-steps">
            <span>01 เลือกเอกสาร</span>
            <span>02 กำหนดการทดสอบ</span>
            <span>03 ตรวจผลและเปรียบเทียบ</span>
          </div>
        </section>
      ) : (
        <div>
          {detailMode && (
            <section className="panel review-summary" aria-label="สรุปชุดทดสอบ">
              <strong className="document-name">{document.filename}</strong>
              <span>หน้า {document.page_number ?? 1}</span>
              <CaseStatus record={testCase!} />
              <span className="muted">
                {new Date(testCase!.created_at).toLocaleString("th-TH")}
              </span>
              <span>
                {testCase!.ground_truth_raw === null
                  ? "รอ Ground Truth"
                  : "มี Ground Truth"}
              </span>
              {testCase!.categories.map((c) => (
                <span className="badge neutral" key={c.code}>
                  {categoryLabel(c)}
                </span>
              ))}
            </section>
          )}
          {!detailMode && (
            <div className="workspace-top">
              <div
                className="segmented"
                role="tablist"
                aria-label="รูปแบบการทดสอบ"
              >
                <button
                  role="tab"
                  aria-selected={testMode === "single"}
                  onClick={() => chooseMode("single")}
                  disabled={!!busy}
                >
                  หน้าเดียว / ROI
                </button>
                {document.document_type === "pdf" && (
                  <button
                    role="tab"
                    aria-selected={testMode === "batch"}
                    onClick={() => chooseMode("batch")}
                    disabled={!!busy}
                  >
                    หลายหน้า PDF
                  </button>
                )}
              </div>
              <span className="muted">
                {document.filename} · {document.page_count} หน้า
              </span>
            </div>
          )}
          {document.document_type === "pdf" &&
            testMode === "batch" &&
            !detailMode && (
              <PdfBatchPanel
                key={document.id}
                documentId={document.id}
                pageCount={document.page_count}
                pipelines={selectedPipelines}
                categoryCodes={categoryCodes}
                disabled={!!busy}
                onBusy={(value) =>
                  setBusy(value ? "ประมวลผลหน้าที่เลือก" : null)
                }
                activePage={document.page_number ?? 1}
                onPreview={changePage}
                onReview={reviewBatchPage}
                runTarget={batchRunTarget}
              />
            )}
          <div id="document-review" className="review-layout">
            <div className="document-column">
              <div
                className={
                  document.document_type === "pdf" && testMode !== "batch"
                    ? "document-with-rail"
                    : ""
                }
              >
                {document.document_type === "pdf" && testMode !== "batch" && (
                  <aside className="page-rail" aria-label="รายการหน้าเอกสาร">
                    <h3>หน้า</h3>
                    {Array.from(
                      { length: Math.min(document.page_count, 20) },
                      (_, i) => {
                        const start =
                          Math.floor(((document.page_number ?? 1) - 1) / 20) *
                          20;
                        return start + i + 1;
                      },
                    )
                      .filter((n) => n <= document.page_count)
                      .map((n) => (
                        <button
                          key={n}
                          className={`button small ${document.page_number === n ? "active" : ""}`}
                          aria-label={`พรีวิวหน้า ${n}`}
                          aria-current={
                            document.page_number === n ? "page" : undefined
                          }
                          disabled={!!busy}
                          onClick={() => changePage(n)}
                        >
                          <span className="page-sheet">{n}</span>หน้า {n}
                        </button>
                      ))}
                  </aside>
                )}
                <section className="panel preview-panel">
                  <div className="panel-header">
                    <h2>
                      <FileImage size={16} />
                      เอกสารต้นฉบับ
                    </h2>
                    <span className="document-info">
                      {document.width} × {document.height} px
                    </span>
                  </div>
                  {document.document_type === "pdf" && (
                    <nav
                      className="pdf-pages"
                      aria-label={t("PDF page navigation")}
                    >
                      <span>{document.page_count} หน้า</span>
                      <button
                        className="button small"
                        aria-label={t("Previous page")}
                        disabled={!!busy || document.page_number === 1}
                        onClick={() => changePage(document.page_number! - 1)}
                      >
                        ‹
                      </button>
                      <span data-testid="pdf-page-indicator" aria-live="polite">
                        {messages.page(
                          document.page_number ?? 1,
                          document.page_count,
                        )}
                      </span>
                      <label className="sr-only" htmlFor="preview-page">
                        {t("Select PDF page")}
                      </label>
                      <select
                        id="preview-page"
                        aria-label={t("Select PDF page")}
                        disabled={!!busy}
                        value={document.page_number ?? 1}
                        onChange={(e) => changePage(Number(e.target.value))}
                      >
                        {Array.from({ length: document.page_count }, (_, i) => (
                          <option key={i + 1}>{i + 1}</option>
                        ))}
                      </select>
                      <button
                        className="button small"
                        aria-label={t("Next page")}
                        disabled={
                          !!busy || document.page_number === document.page_count
                        }
                        onClick={() => changePage(document.page_number! + 1)}
                      >
                        ›
                      </button>
                      <p>
                        เปลี่ยนหน้าแล้วพื้นที่และข้อความที่ยังไม่บันทึกจะถูกล้าง
                      </p>
                    </nav>
                  )}
                  <div style={{ pointerEvents: busy ? "none" : undefined }}>
                    <DocumentViewer
                      key={`${document.id}:${document.page_number ?? 0}`}
                      imageUrl={api.assetUrl(document.image_url)}
                      width={document.width}
                      height={document.height}
                      roi={testMode === "batch" ? null : roi}
                      allowRoi={testMode !== "batch"}
                      onRoiChange={changeRoi}
                      boxes={boxes.filter(
                        (b) =>
                          resultTab === "all" || b.pipelineId === resultTab,
                      )}
                      selectedBoxId={selectedBoxId}
                      onSelectBox={setSelectedBoxId}
                      regionMode={regionMode}
                      onRegionModeChange={setRegionMode}
                      suggestions={suggestions}
                      onSelectSuggestion={(s) => {
                        changeRoi(s.roi);
                        setSuggestions([]);
                      }}
                    />
                  </div>
                  <div className="preview-footer">
                    <span>
                      {testMode === "batch"
                        ? "ทดสอบหลายหน้า · ทุก Pipeline ใช้เต็มหน้า"
                        : roi
                          ? messages.region(roi.x2 - roi.x1, roi.y2 - roi.y1)
                          : "เต็มหน้า · ยังไม่เลือก ROI"}
                    </span>
                    <span>Hutch Full ใช้ภาพเต็มเสมอ</span>
                  </div>
                </section>
              </div>
              {roi && (
                <div className="panel crop-preview">
                  <Image
                    src={api.cropUrl(document.id, roi, document.page_number)}
                    alt={t("Selected test region crop")}
                    width={150}
                    height={65}
                    unoptimized
                  />
                  <div>
                    <strong>พื้นที่ทดสอบ Mint / Hutch Crop</strong>
                    <p>
                      {roi.x2 - roi.x1} × {roi.y2 - roi.y1} px · PNG จาก backend
                    </p>
                  </div>
                </div>
              )}
              {testMode !== "batch" && (
                <section className="panel panel-body mt-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Sparkles size={16} />
                    <strong className="mr-auto">
                      {t("Auto ROI suggestions")}
                    </strong>
                    <select
                      className="select max-w-32"
                      aria-label={t("Auto ROI mode")}
                      value={autoMode}
                      disabled={!!busy}
                      onChange={(e) => setAutoMode(e.target.value)}
                    >
                      <option value="text-line">{t("Text lines")}</option>
                      <option value="layout">{t("Layout")}</option>
                      <option value="hybrid">{t("Hybrid")}</option>
                    </select>
                    <button
                      className="button small"
                      disabled={!!busy}
                      onClick={() =>
                        void act(t("Detecting suggested regions"), async () => {
                          const r = await api.getAutoROIs(
                            document.id,
                            autoMode,
                            document.page_number,
                          );
                          setSuggestions(r.regions);
                          setNotice(
                            r.regions.length
                              ? messages.suggestions(r.regions.length)
                              : t(
                                  "No regions suggested. You can draw a region manually.",
                                ),
                          );
                        })
                      }
                    >
                      {t("Auto Detect")}
                    </button>
                  </div>
                  <p className="filter-note">
                    เลือกกล่องที่แนะนำเพื่อใช้เป็น ROI หรือวาดพื้นที่เองได้
                  </p>
                  {!!suggestions.length && (
                    <div className="flex flex-wrap gap-2 mt-3">
                      {suggestions.map((s, i) => (
                        <button
                          key={s.id}
                          className="button small"
                          onClick={() => {
                            changeRoi(s.roi);
                            setSuggestions([]);
                          }}
                        >
                          พื้นที่ {i + 1}
                        </button>
                      ))}
                      <button
                        className="button small ghost"
                        onClick={() => setSuggestions([])}
                      >
                        {t("Dismiss")}
                      </button>
                    </div>
                  )}
                </section>
              )}
              {!!latestRuns.length && <CropDebugPanel runs={latestRuns} />}
            </div>
            <aside className="inspector">
              {!!latestRuns.length && (
                <section className="results-inspector">
                  <div className="panel-header">
                    <h2>ผล OCR และความแม่นยำ</h2>
                  </div>
                  <div
                    className="segmented mb-3"
                    role="tablist"
                    aria-label="เลือกผล Pipeline"
                  >
                    {pipelines.map((p) => (
                      <button
                        role="tab"
                        key={p.pipeline_id}
                        aria-selected={resultTab === p.pipeline_id}
                        onClick={() => setResultTab(p.pipeline_id)}
                      >
                        {pipelineLabel(p.pipeline_id, p.name)}
                      </button>
                    ))}
                    <button
                      role="tab"
                      aria-selected={resultTab === "all"}
                      onClick={() => setResultTab("all")}
                    >
                      เปรียบเทียบทั้งหมด
                    </button>
                  </div>
                  {visiblePipelines.map((p) => (
                    <PipelineResultCard
                      key={p.pipeline_id}
                      pipeline={p}
                      run={latestRuns.find(
                        (r) => r.pipeline_id === p.pipeline_id,
                      )}
                      selectedBoxId={selectedBoxId}
                      onSelectBox={setSelectedBoxId}
                      running={
                        busy === t("Running pipelines") &&
                        selectedPipelines.includes(p.pipeline_id)
                      }
                      staleMetrics={dirtyGroundTruth}
                    />
                  ))}
                  <p className="filter-note">
                    CER / WER / เวลา ↓ · Exact Match / Confidence ↑<br />
                    CER เป็นตัวหลักสำหรับภาษาไทย WER แบ่งคำด้วยช่องว่าง
                  </p>
                </section>
              )}
              {inlineReview && (
                <div className="notice-banner" role="status">
                  กำลังตรวจผลหน้า {testCase?.page_number} · Ground Truth
                  ของหน้านี้เท่านั้น
                </div>
              )}
              {testMode === "single" || detailMode || inlineReview ? (
                <GroundTruthEditor
                  value={groundTruth}
                  onChange={(value) => {
                    setGroundTruth(value);
                    setGtTouched(true);
                  }}
                  onSave={() => saveTruth(false)}
                  onConfirm={() => saveTruth(true)}
                  disabled={!!busy}
                  canSave={true}
                  status={testCase?.status}
                  dirty={dirtyGroundTruth}
                />
              ) : (
                <section className="panel panel-body">
                  <h2>ข้อความอ้างอิงรายหน้า</h2>
                  <p className="filter-note">
                    หลังประมวลผล เลือกเปิดผลของแต่ละหน้าเพื่อกรอก Ground Truth
                    และตรวจความแม่นยำแยกกัน
                  </p>
                </section>
              )}
              <section className="panel">
                <div className="panel-header">
                  <h2>ประเภทข้อมูล</h2>
                  <span className="muted text-xs">เลือกได้หลายค่า</span>
                </div>
                <div className="panel-body">
                  <CategorySelector
                    categories={categories}
                    selected={categoryCodes}
                    onChange={setCategoryCodes}
                    disabled={!!busy}
                  />
                  <p className="filter-note">
                    ใช้เพื่อวิเคราะห์ผล ไม่ส่งให้โมเดล
                  </p>
                </div>
              </section>
              <section className="panel">
                <div className="panel-header">
                  <h2>Pipeline ที่จะทดสอบ</h2>
                  <Link className="mini-link" href="/settings/pipelines">
                    ตั้งค่า
                  </Link>
                </div>
                <div className="panel-body">
                  <PipelineSelector
                    pipelines={pipelines}
                    selected={selectedPipelines}
                    onChange={setSelectedPipelines}
                    disabled={!!busy}
                  />
                </div>
              </section>
            </aside>
          </div>
          {testMode === "batch" && !detailMode && (
            <div className="run-target" ref={setBatchRunTarget} />
          )}
          {(testMode === "single" || detailMode) && (
            <div className="run-bar">
              <div>
                <strong>{selectedPipelines.length} Pipeline</strong>
                <p>
                  {roi
                    ? "พื้นที่ที่เลือกสำหรับ Mint / Hutch Crop"
                    : "ภาพเต็มหน้า"}{" "}
                  · ผลบันทึกอัตโนมัติเมื่อรันเสร็จ
                </p>
              </div>
              <div>
                <button
                  className="button secondary"
                  disabled={!!busy}
                  onClick={save}
                >
                  {t("Save test case")}
                </button>
                <button
                  className="button secondary"
                  disabled={!!busy || !pipelines.some((p) => p.enabled)}
                  onClick={() =>
                    run(
                      pipelines
                        .filter((p) => p.enabled)
                        .map((p) => p.pipeline_id),
                    )
                  }
                >
                  {t("Run all pipelines")}
                </button>
                <button
                  className="button primary"
                  disabled={!!busy || !selectedPipelines.length}
                  onClick={() => run(selectedPipelines)}
                >
                  {busy === t("Running pipelines")
                    ? "กำลังประมวลผล…"
                    : t("Run selected")}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
