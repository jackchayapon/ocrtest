"use client";
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as api from "@/lib/api";
import type { Category, PipelineConfig } from "@/types";
import { categoryLabel, pipelineLabel, userError } from "@/lib/i18n/th";
import { PageHeader, EmptyState, LoadingState } from "@/components/ConsoleUI";

function unit(value: string | null) {
  if (value === null) return "∅";
  if (value === " ") return "␠ (space)";
  return value;
}
function ErrorAnalysis() {
  const params = useSearchParams();
  const [filters, setFilters] = useState<Record<string, string>>({
    error_level: "char",
    text_kind: "final",
    test_case_id: params.get("test_case_id") ?? "",
    document: params.get("document") ?? "",
  });
  const [pipelines, setPipelines] = useState<PipelineConfig[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [data, setData] = useState<{ total: number; items: api.ErrorGroup[] }>({
    total: 0,
    items: [],
  });
  const [offset, setOffset] = useState(0),
    [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true),
    [working, setWorking] = useState(false);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams(
          Object.entries(filters).filter(([, v]) => v),
        );
        params.set("offset", String(offset));
        params.set("limit", "50");
        const [result, configs, tags] = await Promise.all([
          api.getErrorAnalysis(params),
          api.getPipelines(),
          api.getCategories(),
        ]);
        if (active) {
          setData(result);
          setPipelines(configs);
          setCategories(tags);
        }
      } catch (e) {
        if (active)
          setError(
            userError(e instanceof Error ? e.message : "โหลดข้อมูลไม่สำเร็จ"),
          );
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [filters, offset, revision]);
  function change(key: string, value: string) {
    setOffset(0);
    setFilters((old) => ({ ...old, [key]: value }));
  }
  async function recompute() {
    setWorking(true);
    setError("");
    setNotice("");
    try {
      await api.recomputeErrors(filters.test_case_id);
      setNotice("คำนวณข้อผิดพลาดของชุดทดสอบนี้แล้ว");
      setRevision((n) => n + 1);
    } catch (e) {
      setError(userError(e instanceof Error ? e.message : "คำนวณไม่สำเร็จ"));
    } finally {
      setWorking(false);
    }
  }
  return (
    <div className="page-stack">
      <PageHeader
        title="วิเคราะห์ข้อผิดพลาด OCR"
        description="การแทนที่ การตกหล่น และการแทรก · ผลล่าสุดต่อชุดทดสอบและ Pipeline"
      />
      <section className="panel panel-body">
        <div className="flex flex-wrap gap-3">
          <label>
            Pipeline
            <select
              aria-label="Pipeline"
              className="select"
              value={filters.pipeline ?? ""}
              onChange={(e) => change("pipeline", e.target.value)}
            >
              <option value="">ทั้งหมด</option>
              {pipelines.map((p) => (
                <option key={p.pipeline_id} value={p.pipeline_id}>
                  {pipelineLabel(p.pipeline_id, p.name)}
                </option>
              ))}
            </select>
          </label>
          <label>
            ประเภทข้อมูล
            <select
              aria-label="ประเภทข้อมูล"
              className="select"
              value={filters.category ?? ""}
              onChange={(e) => change("category", e.target.value)}
            >
              <option value="">ทั้งหมด</option>
              {categories.map((c) => (
                <option key={c.code} value={c.code}>
                  {categoryLabel(c)}
                </option>
              ))}
            </select>
          </label>
          <label>
            ข้อผิดพลาด
            <select
              aria-label="ข้อผิดพลาด"
              className="select"
              value={filters.error_type ?? ""}
              onChange={(e) => change("error_type", e.target.value)}
            >
              <option value="">ทั้งหมด</option>
              {["substitution", "deletion", "insertion"].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
          <label>
            ระดับ
            <select
              aria-label="ระดับ"
              className="select"
              value={filters.error_level}
              onChange={(e) => change("error_level", e.target.value)}
            >
              <option value="char">ตัวอักษร (CER)</option>
              <option value="word">คำ (WER)</option>
            </select>
          </label>
          <label>
            ข้อความ OCR
            <select
              aria-label="ข้อความ OCR"
              className="select"
              value={filters.text_kind}
              onChange={(e) => change("text_kind", e.target.value)}
            >
              <option value="final">Final</option>
              <option value="raw">Raw</option>
            </select>
          </label>
          <label>
            Test Case ID
            <input
              className="input"
              value={filters.test_case_id ?? ""}
              onChange={(e) => change("test_case_id", e.target.value)}
            />
          </label>
          <label>
            Document ID
            <input
              className="input"
              value={filters.document ?? ""}
              onChange={(e) => change("document", e.target.value)}
            />
          </label>
          <button
            className="button secondary"
            onClick={() => {
              setFilters({ error_level: "char", text_kind: "final" });
              setOffset(0);
            }}
          >
            ล้างตัวกรอง
          </button>
        </div>
        <p className="filter-note">
          ใช้ NFC และการเว้นวรรคแบบเดียวกับ CER/WER เดิม · WER
          แบ่งคำด้วยช่องว่าง จึงมีข้อจำกัดสำหรับภาษาไทย · ∅
          หมายถึงไม่มีหน่วยข้อความ
        </p>
        <p className="filter-note">
          ผลเก่าอาจยังไม่มีรายละเอียด เลือก Test Case
          แล้วคำนวณใหม่ได้โดยไม่เรียก OCR
        </p>
        {filters.test_case_id && (
          <button
            className="button secondary mt-3"
            disabled={working || loading}
            onClick={() => void recompute()}
          >
            คำนวณรายละเอียดใหม่
          </button>
        )}
      </section>
      {notice && (
        <div className="notice-banner" role="status">
          {notice}
        </div>
      )}
      {error && (
        <div className="error-banner" role="alert">
          {error}{" "}
          <button
            className="button small"
            onClick={() => setRevision((n) => n + 1)}
          >
            ลองใหม่
          </button>
        </div>
      )}
      {loading ? (
        <LoadingState label="กำลังโหลดข้อผิดพลาด…" />
      ) : (
        !error &&
        (data.items.length ? (
          <section className="panel">
            <div className="panel-header">
              <h2>{data.total} รูปแบบข้อผิดพลาด</h2>
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    {[
                      "Pipeline",
                      "Error Type",
                      "Ground Truth",
                      "OCR",
                      "Count",
                      "เอกสาร / ชุดทดสอบ / ประเภท",
                    ].map((h) => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((row, i) => (
                    <tr key={i}>
                      <td>
                        {pipelineLabel(
                          row.pipeline_id,
                          pipelines.find(
                            (p) => p.pipeline_id === row.pipeline_id,
                          )?.name ?? row.pipeline_id,
                        )}
                      </td>
                      <td>{row.error_type}</td>
                      <td
                        title={
                          row.ground_truth_unit
                            ? Array.from(row.ground_truth_unit)
                                .map(
                                  (c) =>
                                    `U+${c.codePointAt(0)!.toString(16).toUpperCase().padStart(4, "0")}`,
                                )
                                .join(" ")
                            : undefined
                        }
                      >
                        {unit(row.ground_truth_unit)}
                      </td>
                      <td>{unit(row.ocr_unit)}</td>
                      <td>{row.count}</td>
                      <td>
                        <details>
                          <summary>{row.test_case_count} ชุดทดสอบ</summary>
                          {row.cases.map((c) => (
                            <p key={c.id}>
                              <Link
                                className="mini-link"
                                href={`/test/${c.id}`}
                              >
                                {c.filename}
                                {c.page_number
                                  ? ` · หน้า ${c.page_number}`
                                  : ""}{" "}
                                · {c.id.slice(0, 8)}
                              </Link>
                              <br />
                              {c.categories
                                .map((tag) =>
                                  categoryLabel({
                                    code: tag,
                                    display_name: tag,
                                  }),
                                )
                                .join(", ") || "ไม่ระบุประเภท"}
                            </p>
                          ))}
                          {row.test_case_count > row.cases.length && (
                            <p className="muted">
                              แสดง 20 รายการแรก · กรองเอกสารเพื่อเจาะจงข้อมูล
                            </p>
                          )}
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="panel-body flex items-center gap-3">
              <button
                className="button secondary"
                disabled={!offset}
                onClick={() => setOffset((n) => n - 50)}
              >
                ก่อนหน้า
              </button>
              <span>
                {offset + 1}–{offset + data.items.length}
              </span>
              <button
                className="button secondary"
                disabled={offset + 50 >= data.total}
                onClick={() => setOffset((n) => n + 50)}
              >
                ถัดไป
              </button>
            </div>
          </section>
        ) : (
          <EmptyState
            title="ยังไม่มีรายละเอียดข้อผิดพลาด"
            description="ยืนยันหรือบันทึก Ground Truth หลังรัน OCR หรือคำนวณรายละเอียดของชุดทดสอบเก่าใหม่"
          />
        ))
      )}
    </div>
  );
}

export default function ErrorAnalysisPage() {
  return (
    <Suspense fallback={<LoadingState label="กำลังโหลดข้อผิดพลาด…" />}>
      <ErrorAnalysis />
    </Suspense>
  );
}
