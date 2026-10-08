"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCw } from "lucide-react";
import { getAnalyticsSummary, getHistory, getComparison, getMatrix, getPipelines } from "@/lib/api";
import { useComparisonDisplay } from "@/lib/analytics-scope";
import {BestCerBadge, testMinimumCer, latestTestRun, isMinimumCer} from "@/components/BestCer";
import {currentComparisonNames} from "@/lib/comparison-identity";
import {ByType} from "@/components/ComparisonDecision";
import { ComparisonHero, PipelineRanking, DocumentTypeWinners, PipelineSideBySide } from "@/components/ComparisonDashboard";
import type {Comparison} from "@/types/comparison";
import { pipelineLabel, userError } from "@/lib/i18n/th";
import type {
  AnalyticsSummary,
  TestCase,
  PipelineConfig,
  MatrixRow,
} from "@/types";
import { percent } from "@/components/MatrixTable";
import {
  LoadingState,
  EmptyState,
} from "@/components/ConsoleUI";
export default function MatrixPage() {
  const [cases, setCases] = useState<TestCase[]>([]),
    [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const display = useComparisonDisplay();
  const [decision, setDecision] = useState<Comparison|null>(null);
  const [configs,setConfigs]=useState<PipelineConfig[]>([]);
  const [matrix,setMatrix]=useState<MatrixRow[]>([]);
  const [chosenPair,setChosenPair]=useState<[string,string]|null>(null);
  const [offset, setOffset] = useState(0),
    [hasNext, setHasNext] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [revision, setRevision] = useState(0);

  useEffect(()=>{
    const refresh=()=>setRevision(n=>n+1);
    window.addEventListener("focus",refresh);
    return()=>window.removeEventListener("focus",refresh);
  },[]);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError("");

      await Promise.all([
        getHistory({ limit: 21, offset }, controller.signal),
        getAnalyticsSummary({}, controller.signal),
        getComparison({}, false, controller.signal),
        getPipelines(),
        getMatrix({}, controller.signal),
      ])
        .then(([h, s, d, config, m]) => {
          if (active) {
            setCases(h.slice(0, 20));
            setHasNext(h.length > 20);
            setSummary(s);
            // Current names/settings are authoritative. Historical identities retain their saved names.
            setDecision(currentComparisonNames(d,config));
            setConfigs(config);
            setMatrix(m);
          }
        })
        .catch((e) => {
          if (active) setError(userError(e.message));
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }
    void load();
    return () => {
      active = false;
      controller.abort();
    };
  }, [offset, revision]);
  const visible = cases;
  const selected = decision?.pipelines ?? [];
  const identities=decision?.pipelines??[];
  const defaults:[string,string]=[decision?.overall.recommendation??decision?.overall.ranking[0]?.pipeline_id??identities[0]?.pipeline_id??"",decision?.overall.ranking[1]?.pipeline_id??identities[1]?.pipeline_id??""];
  const pair:[string,string]=chosenPair&&chosenPair.every(id=>identities.some(p=>p.pipeline_id===id))?chosenPair:defaults;
  const compare=(id?:string)=>{
    if(id)setChosenPair([id,identities.find(p=>p.pipeline_id!==id)?.pipeline_id??""]);
    document.getElementById("compare-results")?.scrollIntoView({behavior:"smooth"});
  };
  return (
    <div className="page-stack comparison-page">
      <div className="comparison-top"><div><h1>OCR Pipeline Comparison</h1><p>เปรียบเทียบ OCR Pipeline จากผลทดสอบบนเอกสารจริง</p></div></div>
      <div className="comparison-section-head"><div role="tablist" aria-label="มุมมองการเปรียบเทียบ" className="comparison-tabs"><button role="tab" aria-selected={display.view === "overall"} onClick={()=>display.update("view","overall")}>สรุปผล</button><button role="tab" aria-selected={display.view === "by-type"} onClick={()=>display.update("view","by-type")}>ตามประเภทเอกสาร</button></div><button className="button secondary" disabled={loading} onClick={()=>setRevision(n=>n+1)}><RefreshCw size={16}/>รีเฟรช</button></div>
      {error && (
        <div className="error-banner" role="alert">
          ไม่สามารถโหลดผลเปรียบเทียบได้: {error}{" "}
          <button
            className="button small"
            onClick={() => setRevision((n) => n + 1)}
          >
            ลองใหม่
          </button>
        </div>
      )}
      {loading ? (
        <LoadingState label="กำลังโหลดผลเปรียบเทียบ…" />
      ) : (
        !error && (
          <>
            {decision && (display.view === "overall" ? <>
              <ComparisonHero data={decision} rows={matrix} onCompare={()=>compare()}/>
              <div className="comparison-main-grid"><PipelineRanking data={decision} configs={configs} rows={matrix} onCompare={compare}/><DocumentTypeWinners data={decision} onAll={()=>display.update("view","by-type")}/></div>
              <PipelineSideBySide key={offset} data={decision} cases={cases} pair={pair} setPair={setChosenPair} hasNext={hasNext} onNextPage={()=>setOffset(n=>n+20)}/>
            </> : <ByType data={decision}/>)}
            <details className="panel panel-body"><summary className="cursor-pointer font-semibold">เปรียบเทียบรายชุดทดสอบ</summary>
            <p className="filter-note">สีเขียวแสดง CER ต่ำสุดในแถว ไม่ใช่ผู้ชนะโดยรวม</p>
            {cases.length ? (
              <section className="panel">
                <div className="panel-header">
                  <div>
                    <h2>เปรียบเทียบรายชุดทดสอบ</h2>
                    <p className="filter-note">
                      ผลล่าสุดต่อ Pipeline · ช่องที่ไม่มี Ground Truth แสดง —
                    </p>
                  </div>
                </div>
                {visible.length ? (
                  <div
                    className="table-wrap"
                    tabIndex={0}
                    role="region"
                    aria-label="ตารางข้อมูล เลื่อนแนวนอนเพื่อดูคอลัมน์เพิ่มเติม"
                  >
                    <table
                      className="data-table"
                      style={{ minWidth: 900 }}
                      aria-label="เปรียบเทียบรายชุดทดสอบ"
                    >
                      <thead>
                        <tr>
                          <th scope="col">เอกสาร / หน้า</th>
                          {selected.map((p) => (
                            <th scope="col" key={p.pipeline_id}>
                              {pipelineLabel(p.pipeline_id, p.pipeline_name)}{p.retired && <span className="badge neutral">เก็บถาวร</span>}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {visible.map((c) => {
                          const best = testMinimumCer(c, selected.map(p => p.pipeline_id));
                          return (
                          <tr key={c.id}>
                            <td>
                              <Link
                                className="row-title"
                                href={`/test/${c.id}`}
                              >
                                {c.document.filename}
                              </Link>
                              <span className="row-meta">
                                หน้า {c.page_number ?? 1} ·{" "}
                                {c.ground_truth_raw === null
                                  ? "รอ Ground Truth"
                                  : "มี Ground Truth"}
                              </span>
                            </td>
                            {selected.map((p) => {
                              const r = latestTestRun(c, p.pipeline_id);
                              const isBest = r?.status === "success" && isMinimumCer(r.metrics?.cer, best.minimum);
                              return (
                                <td key={p.pipeline_id} className={isBest ? "comparison-cer-best" : r?.status === "error" ? "comparison-cer-error" : !r || r.metrics?.cer == null ? "comparison-cer-missing" : undefined}>
                                  {!r ? (
                                    <span className="muted">ยังไม่ทดสอบ</span>
                                  ) : r.status === "error" ? (
                                    <span className="badge error">ประมวลผลไม่สำเร็จ</span>
                                  ) : (
                                    <>
                                      <strong>
                                        CER ของชุดทดสอบนี้ {percent(r.metrics?.cer)}
                                        {isBest && <BestCerBadge tied={best.tied}/>}
                                      </strong>
                                      <span className="row-meta">
                                        WER {percent(r.metrics?.wer)} · Exact{" "}
                                        {r.metrics
                                          ? r.metrics.exact_match
                                            ? "ใช่"
                                            : "ไม่ใช่"
                                          : "—"}
                                      </span>
                                      <span className="row-meta">
                                        {r.processing_time_ms ?? "—"} ms ·
                                        Confidence {percent(r.confidence)}
                                      </span>
                                    </>
                                  )}
                                </td>
                              );
                            })}
                          </tr>
                        );})}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyState
                    title="ไม่มีชุดทดสอบตามตัวกรองในหน้านี้"
                    description="ลองล้างการค้นหา หรือเปลี่ยนหน้าตาราง"
                  />
                )}
                <div className="table-footer">
                  <span>
                    หน้า {offset / 20 + 1} · แสดง {visible.length} รายการในหน้านี้ จาก {summary?.history_cases ?? "—"} ชุดที่เคยรัน
                  </span>
                  <div>
                    <button
                      className="button secondary"
                      disabled={!offset}
                      onClick={() => setOffset((n) => Math.max(0, n - 20))}
                    >
                      ก่อนหน้า
                    </button>
                    <button
                      className="button secondary"
                      disabled={!hasNext}
                      onClick={() => setOffset((n) => n + 20)}
                    >
                      ถัดไป
                    </button>
                  </div>
                </div>
              </section>
            ) : (
              <section className="panel">
                <EmptyState
                  title="ยังไม่มีผลสำหรับเปรียบเทียบ"
                  description="รัน OCR และบันทึก Ground Truth เพื่อเริ่มเปรียบเทียบความแม่นยำ"
                  action={
                    <Link className="button primary" href="/">
                      เริ่มทดสอบ OCR
                    </Link>
                  }
                />
              </section>
            )}
            <p className="filter-note">
              CER / WER / เวลา: ต่ำดีกว่า · Exact Match / Confidence: สูงดีกว่า
              · เปรียบเทียบจำนวนตัวอย่างเสมอ โดยเฉพาะเมื่อ Pipeline
              มีผลสำเร็จไม่เท่ากัน
            </p>
            </details>
          </>
        )
      )}
    </div>
  );
}
