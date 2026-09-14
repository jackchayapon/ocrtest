"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCw } from "lucide-react";
import { getCategories, getMatrix, getPipelines, getHistory } from "@/lib/api";
import { pipelineLabel, userError } from "@/lib/i18n/th";
import type {
  Category,
  MatrixRow,
  PipelineConfig,
  QueryFilters,
  TestCase,
} from "@/types";
import MatrixTable, { percent } from "@/components/MatrixTable";
import {
  PageHeader,
  FilterBar,
  DatasetFilters,
  LoadingState,
  EmptyState,
  Stat,
} from "@/components/ConsoleUI";
export default function MatrixPage() {
  const [rows, setRows] = useState<MatrixRow[]>([]),
    [cases, setCases] = useState<TestCase[]>([]),
    [categories, setCategories] = useState<Category[]>([]),
    [pipelines, setPipelines] = useState<PipelineConfig[]>([]);
  const [filters, setFilters] = useState<QueryFilters>({}),
    [offset, setOffset] = useState(0),
    [hasNext, setHasNext] = useState(false),
    [search, setSearch] = useState(""),
    [onlyGT, setOnlyGT] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [revision, setRevision] = useState(0);
  const invalid = !!(
    filters.date_from &&
    filters.date_to &&
    filters.date_from > filters.date_to
  );
  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError("");
      if (invalid) {
        setLoading(false);
        return;
      }
      await Promise.all([
        getMatrix(filters),
        getHistory({ ...filters, limit: 21, offset }),
        getCategories(),
        getPipelines(),
      ])
        .then(([r, h, c, p]) => {
          if (active) {
            setRows(r);
            setCases(h.slice(0, 20));
            setHasNext(h.length > 20);
            setCategories(c);
            setPipelines(p);
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
    };
  }, [filters, offset, revision, invalid]);
  const best = rows
    .filter((r) => r.cer !== null)
    .sort((a, b) => a.cer! - b.cer!)[0];
  const fastest = rows
    .filter((r) => r.avg_time_ms !== null && r.successful_runs > 0)
    .sort((a, b) => a.avg_time_ms! - b.avg_time_ms!)[0];
  const visible = cases.filter(
    (c) =>
      (!onlyGT || c.ground_truth_raw !== null) &&
      (!search ||
        c.document.filename.toLowerCase().includes(search.toLowerCase())),
  );
  const selected = pipelines.filter(
    (p) => !filters.pipeline || p.pipeline_id === filters.pipeline,
  );
  return (
    <div className="page-stack">
      <PageHeader
        title="เปรียบเทียบ Pipeline"
        description="ดูผลแต่ละชุดทดสอบควบคู่กับค่าความแม่นยำและเวลาจากชุดข้อมูลเดียวกัน"
        actions={
          <button
            className="button secondary"
            disabled={loading}
            onClick={() => setRevision((n) => n + 1)}
          >
            <RefreshCw size={16} />
            รีเฟรช
          </button>
        }
      />
      <FilterBar
        count={
          Object.values(filters).filter(Boolean).length +
          Number(!!search) +
          Number(onlyGT)
        }
        onClear={() => {
          setFilters({});
          setSearch("");
          setOnlyGT(false);
          setOffset(0);
        }}
      >
        <DatasetFilters
          value={filters}
          categories={categories}
          pipelines={pipelines}
          onChange={(k, v) => {
            setFilters((old) => ({ ...old, [k]: v || undefined }));
            setOffset(0);
          }}
        />
        <label className="field">
          ค้นหาเอกสารในหน้านี้
          <input
            className="input"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="ชื่อเอกสาร"
          />
        </label>
        <label className="field">
          Document ID
          <input
            className="input"
            value={filters.document || ""}
            onChange={(e) => {
              setFilters((old) => ({
                ...old,
                document: e.target.value || undefined,
              }));
              setOffset(0);
            }}
            placeholder="UUID"
          />
        </label>
      </FilterBar>
      {invalid && (
        <p className="error-banner" role="alert">
          วันที่สิ้นสุดต้องไม่อยู่ก่อนวันเริ่มต้น
        </p>
      )}
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
        !invalid &&
        !error && (
          <>
            <div className="stat-grid">
              <Stat
                label="ชุดทดสอบในหน้าตารางนี้"
                value={cases.length}
                note={`มี Ground Truth ${cases.filter((c) => c.ground_truth_raw !== null).length} ชุด`}
              />
              <Stat
                label="ผลที่ประเมินความแม่นยำแล้ว"
                value={rows.reduce((n, r) => n + r.evaluated_runs, 0)}
                note="จำนวนผลจากทุก Pipeline ตามตัวกรอง API"
              />
              <Stat
                label="CER ต่ำที่สุด ↓"
                value={percent(best?.cer)}
                note={
                  best
                    ? pipelineLabel(best.pipeline_id, best.pipeline_name)
                    : "ต้องมี Ground Truth"
                }
              />
              <Stat
                label="Pipeline ที่เร็วที่สุด ↓"
                value={fastest ? `${Math.round(fastest.avg_time_ms!)} ms` : "—"}
                note={
                  fastest
                    ? pipelineLabel(fastest.pipeline_id, fastest.pipeline_name)
                    : "ยังไม่มีผลสำเร็จ"
                }
              />
            </div>
            {cases.length ? (
              <section className="panel">
                <div className="panel-header">
                  <div>
                    <h2>เปรียบเทียบรายชุดทดสอบ</h2>
                    <p className="filter-note">
                      ผลล่าสุดต่อ Pipeline · ช่องที่ไม่มี Ground Truth แสดง —
                    </p>
                  </div>
                  <label className="flex gap-2 text-sm items-center">
                    <input
                      type="checkbox"
                      checked={onlyGT}
                      onChange={(e) => setOnlyGT(e.target.checked)}
                    />
                    เฉพาะชุดที่มี Ground Truth ในหน้านี้
                  </label>
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
                              {pipelineLabel(p.pipeline_id, p.name)}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {visible.map((c) => (
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
                              const r = [...c.runs]
                                .reverse()
                                .find((r) => r.pipeline_id === p.pipeline_id);
                              return (
                                <td key={p.pipeline_id}>
                                  {!r ? (
                                    <span className="muted">ยังไม่ทดสอบ</span>
                                  ) : r.status === "error" ? (
                                    <Link
                                      className="badge error"
                                      href={`/logs?test_case_id=${c.id}`}
                                    >
                                      ผิดพลาด · ดู Log
                                    </Link>
                                  ) : (
                                    <>
                                      <strong>
                                        CER {percent(r.metrics?.cer)}
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
                        ))}
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
                    หน้า {offset / 20 + 1} · {visible.length} ชุด
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
            {rows.some((r) => r.tests > 0) && (
              <section className="panel">
                <div className="panel-header">
                  <h2>ภาพรวมตามตัวกรองข้อมูล</h2>
                  <span className="muted text-xs">
                    ค่าจาก API · ไม่รวมตัวกรองเฉพาะหน้าตาราง
                  </span>
                </div>
                <MatrixTable rows={rows} />
              </section>
            )}
            <p className="filter-note">
              CER / WER / เวลา: ต่ำดีกว่า · Exact Match / Confidence: สูงดีกว่า
              · เปรียบเทียบจำนวนตัวอย่างเสมอ โดยเฉพาะเมื่อ Pipeline
              มีผลสำเร็จไม่เท่ากัน
            </p>
          </>
        )
      )}
    </div>
  );
}
