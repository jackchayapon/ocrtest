"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCw } from "lucide-react";
import { getCategoryAnalytics, getCategories, getPipelines } from "@/lib/api";
import { categoryLabel, pipelineLabel, userError } from "@/lib/i18n/th";
import type {
  CategoryAnalytics,
  Category,
  PipelineConfig,
  QueryFilters,
} from "@/types";
import { percent } from "@/components/MatrixTable";
import {
  PageHeader,
  FilterBar,
  DatasetFilters,
  LoadingState,
  EmptyState,
  Stat,
} from "@/components/ConsoleUI";
export default function CategoryAnalyticsPage() {
  const [data, setData] = useState<CategoryAnalytics[]>([]),
    [categories, setCategories] = useState<Category[]>([]),
    [pipelines, setPipelines] = useState<PipelineConfig[]>([]),
    [filters, setFilters] = useState<QueryFilters>({}),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [revision, setRevision] = useState(0),
    [showUntested, setShowUntested] = useState(false);
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
        getCategoryAnalytics(filters),
        getCategories(),
        getPipelines(),
      ])
        .then(([d, c, p]) => {
          if (active) {
            setData(d);
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
  }, [filters, invalid, revision]);
  const visible = data.filter((c) => showUntested || c.test_cases > 0);
  return (
    <div className="page-stack">
      <PageHeader
        title="วิเคราะห์ตามประเภทข้อมูล"
        description="ค้นหาว่าแต่ละ Pipeline ทำงานได้ดีเพียงใดกับประเภทเอกสารที่คุณกำหนด"
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
          Object.values(filters).filter(Boolean).length + Number(showUntested)
        }
        onClear={() => {
          setFilters({});
          setShowUntested(false);
        }}
      >
        <DatasetFilters
          value={filters}
          categories={categories}
          pipelines={pipelines}
          onChange={(k, v) =>
            setFilters((old) => ({ ...old, [k]: v || undefined }))
          }
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={showUntested}
            onChange={(e) => setShowUntested(e.target.checked)}
          />
          แสดงประเภทที่ยังไม่ทดสอบ
        </label>
      </FilterBar>
      {invalid && (
        <div className="error-banner" role="alert">
          วันที่สิ้นสุดต้องไม่อยู่ก่อนวันเริ่มต้น
        </div>
      )}
      {error && (
        <div className="error-banner" role="alert">
          ไม่สามารถโหลดข้อมูลวิเคราะห์ได้: {error}{" "}
          <button
            className="button small"
            onClick={() => setRevision((n) => n + 1)}
          >
            ลองใหม่
          </button>
        </div>
      )}
      {loading ? (
        <LoadingState label="กำลังโหลดข้อมูลวิเคราะห์…" />
      ) : (
        !error &&
        !invalid && (
          <>
            <div className="stat-grid">
              <Stat label="ประเภทข้อมูลในมุมมองนี้" value={data.length} />
              <Stat
                label="ประเภทที่มีชุดทดสอบ"
                value={data.filter((c) => c.test_cases > 0).length}
              />
              <Stat
                label="ประเภทที่มีผลประเมิน GT"
                value={
                  data.filter((c) =>
                    c.pipelines.some((p) => p.evaluated_runs > 0),
                  ).length
                }
              />
              <Stat
                label="จำนวนการติดประเภทข้อมูล"
                value={data.reduce((s, c) => s + c.test_cases, 0)}
                note="ชุดทดสอบหนึ่งชุดอยู่ได้หลายประเภท"
              />
            </div>
            {visible.length ? (
              <section className="panel">
                <div className="panel-header">
                  <h2>ประสิทธิภาพแยกตามประเภท</h2>
                  <span className="muted text-xs">
                    คลิกประเภทเพื่อเปิดประวัติที่เกี่ยวข้อง
                  </span>
                </div>
                <div
                  className="table-wrap"
                  tabIndex={0}
                  role="region"
                  aria-label="ตารางข้อมูล เลื่อนแนวนอนเพื่อดูคอลัมน์เพิ่มเติม"
                >
                  <table className="data-table" style={{ minWidth: 1050 }}>
                    <caption className="sr-only">
                      จำนวนตัวอย่างและความแม่นยำต่อประเภทและ Pipeline
                    </caption>
                    <thead>
                      <tr>
                        {[
                          "ประเภท / ชุดทดสอบ",
                          "Pipeline",
                          "ตัวอย่าง / มี GT",
                          "สำเร็จ / ผิดพลาด",
                          "CER ↓",
                          "WER ↓",
                          "Exact ↑",
                          "เวลาเฉลี่ย ↓",
                          "Confidence ↑",
                        ].map((h) => (
                          <th key={h} scope="col">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {visible.flatMap((c) =>
                        c.pipelines.map((p, i) => (
                          <tr key={`${c.code}:${p.pipeline_id}`}>
                            {i === 0 && (
                              <td rowSpan={c.pipelines.length}>
                                <Link
                                  href={`/history?category=${encodeURIComponent(c.code)}`}
                                  className="row-title"
                                >
                                  {categoryLabel(c)}
                                </Link>
                                <span className="row-meta">
                                  {c.test_cases} ชุดทดสอบ
                                </span>
                              </td>
                            )}
                            <td>
                              {pipelineLabel(p.pipeline_id, p.pipeline_name)}
                            </td>
                            <td className="numeric">
                              {p.tests} / {p.evaluated_runs}
                            </td>
                            <td className="numeric">
                              {p.successful_runs} /{" "}
                              <span
                                className={p.failed_runs ? "text-red-700" : ""}
                              >
                                {p.failed_runs}
                              </span>
                            </td>
                            <td className="numeric">{percent(p.cer)}</td>
                            <td className="numeric">{percent(p.wer)}</td>
                            <td className="numeric">
                              {percent(p.exact_match_rate)}
                            </td>
                            <td className="numeric">
                              {p.avg_time_ms === null
                                ? "—"
                                : `${Math.round(p.avg_time_ms)} ms`}
                            </td>
                            <td className="numeric">
                              {percent(p.avg_confidence)}
                            </td>
                          </tr>
                        )),
                      )}
                    </tbody>
                  </table>
                </div>
              </section>
            ) : (
              <section className="panel">
                <EmptyState
                  title="ยังไม่มีข้อมูลเพียงพอสำหรับวิเคราะห์"
                  description="กำหนดประเภทข้อมูลให้ชุดทดสอบ แล้วรัน OCR และบันทึก Ground Truth"
                  action={
                    <Link className="button primary" href="/">
                      เริ่มทดสอบ OCR
                    </Link>
                  }
                />
              </section>
            )}
            <p className="filter-note">
              ประเภทข้อมูลเป็น metadata เท่านั้น ไม่ส่งให้โมเดล ·
              ค่าเฉลี่ยใช้ตัวอย่างที่มีข้อมูลจริง และแสดง — เมื่อไม่มี GT /
              confidence · จำนวนการติดประเภทไม่ใช่จำนวนชุดทดสอบที่ไม่ซ้ำกัน
            </p>
          </>
        )
      )}
    </div>
  );
}
