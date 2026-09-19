"use client";
import { useEffect, useState } from "react";
import { RefreshCw, Copy } from "lucide-react";
import { getLogs, getPipelines, type AppLog } from "@/lib/api";
import type { PipelineConfig } from "@/types";
import {
  PageHeader,
  FilterBar,
  LoadingState,
  EmptyState,
} from "@/components/ConsoleUI";
export default function LogsPage() {
  const [pipelines, setPipelines] = useState<PipelineConfig[]>([]);
  const [filters, setFilters] = useState<Record<string, string>>({}),
    [offset, setOffset] = useState(0),
    [revision, setRevision] = useState(0),
    [items, setItems] = useState<AppLog[]>([]),
    [total, setTotal] = useState(0),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [copied, setCopied] = useState("");
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
      const q = new URLSearchParams({ limit: "25", offset: String(offset) });
      const id = new URLSearchParams(window.location.search).get(
        "test_case_id",
      );
      if (id) q.set("test_case_id", id);
      Object.entries(filters).forEach(([k, v]) => {
        if (v) q.set(k, k.startsWith("date_") ? new Date(v).toISOString() : v);
      });
      await Promise.all([getLogs(q), getPipelines()])
        .then(([d, configs]) => {
          if (active) {
            setItems(d.items);
            setPipelines(configs);
            setTotal(d.total);
          }
        })
        .catch(() => {
          if (active)
            setError(
              "ไม่สามารถโหลดบันทึกระบบได้ กรุณาตรวจการเชื่อมต่อ Backend",
            );
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
  function filter(k: string, v: string) {
    setOffset(0);
    setFilters((old) => ({ ...old, [k]: v }));
  }
  return (
    <div className="page-stack">
      <PageHeader
        title="บันทึกการทำงาน"
        description="ตรวจสถานะ ข้อผิดพลาด และรหัสอ้างอิงสำหรับวิเคราะห์ปัญหา"
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
        count={Object.values(filters).filter(Boolean).length}
        onClear={() => {
          setFilters({});
          setOffset(0);
        }}
      >
        <label className="field">
          ระดับ
          <select
            aria-label="ระดับ"
            className="select"
            value={filters.level || ""}
            onChange={(e) => filter("level", e.target.value)}
          >
            <option value="">ทุกระดับ</option>
            {["INFO", "WARNING", "ERROR"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <label className="field">
          Pipeline
          <select
            aria-label="Pipeline"
            className="select"
            value={filters.pipeline || ""}
            onChange={(e) => filter("pipeline", e.target.value)}
          >
            <option value="">ทุก Pipeline</option>
            {pipelines.map((p) => (
              <option key={p.pipeline_id} value={p.pipeline_id}>{p.name}</option>
            ))}
          </select>
        </label>
        <label className="field">
          เหตุการณ์
          <input
            className="input"
            placeholder="เช่น ocr_run_error"
            value={filters.event_type || ""}
            onChange={(e) => filter("event_type", e.target.value)}
          />
        </label>
        <label className="field">
          Request ID
          <input
            className="input"
            value={filters.request_id || ""}
            onChange={(e) => filter("request_id", e.target.value)}
          />
        </label>
        <label className="field">
          ตั้งแต่
          <input
            type="datetime-local"
            className="input"
            value={filters.date_from || ""}
            onChange={(e) => filter("date_from", e.target.value)}
          />
        </label>
        <label className="field">
          ถึง
          <input
            type="datetime-local"
            className="input"
            value={filters.date_to || ""}
            onChange={(e) => filter("date_to", e.target.value)}
          />
        </label>
      </FilterBar>
      {invalid && (
        <p className="error-banner" role="alert">
          เวลาสิ้นสุดต้องไม่อยู่ก่อนเวลาเริ่มต้น
        </p>
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
      {copied && (
        <p role="status" className="notice-banner">
          {copied}
        </p>
      )}
      <section className="panel">
        {loading ? (
          <LoadingState label="กำลังโหลดบันทึก…" />
        ) : (
          !error &&
          !invalid &&
          (items.length ? (
            <div
              className="table-wrap"
              tabIndex={0}
              role="region"
              aria-label="ตารางข้อมูล เลื่อนแนวนอนเพื่อดูคอลัมน์เพิ่มเติม"
            >
              <table className="data-table" style={{ minWidth: 1100 }}>
                <caption className="sr-only">
                  บันทึกกิจกรรม เรียงจากล่าสุด
                </caption>
                <thead>
                  <tr>
                    {[
                      "เวลา",
                      "Level",
                      "Event",
                      "หน้า",
                      "Pipeline",
                      "Request ID",
                      "ข้อความ",
                    ].map((h) => (
                      <th scope="col" key={h}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <time dateTime={row.created_at}>
                          {new Date(row.created_at).toLocaleString("th-TH")}
                        </time>
                      </td>
                      <td>
                        <span
                          className={`badge ${row.level === "ERROR" ? "error" : row.level === "WARNING" ? "warning" : "neutral"}`}
                        >
                          {row.level}
                        </span>
                      </td>
                      <td className="id-text">{row.event_type}</td>
                      <td>{row.page_number ?? "—"}</td>
                      <td>{row.pipeline_id ?? "—"}</td>
                      <td>
                        <code className="id-text">
                          {row.request_id ?? row.gateway_request_id ?? "—"}
                        </code>
                        {(row.request_id || row.gateway_request_id) && (
                          <button
                            className="button small ghost"
                            aria-label="คัดลอก Request ID"
                            onClick={() =>
                              void navigator.clipboard
                                .writeText(
                                  row.request_id ||
                                    row.gateway_request_id ||
                                    "",
                                )
                                .then(() => setCopied("คัดลอก Request ID แล้ว"))
                                .catch(() =>
                                  setCopied(
                                    "คัดลอกไม่ได้ กรุณาเลือกข้อความแล้วคัดลอกด้วยตนเอง",
                                  ),
                                )
                            }
                          >
                            <Copy size={13} />
                          </button>
                        )}
                        {row.gateway_request_id &&
                          row.gateway_request_id !== row.request_id && (
                            <span className="row-meta id-text">
                              Gateway: {row.gateway_request_id}
                            </span>
                          )}
                      </td>
                      <td>
                        {row.message}
                        {row.metadata.error_code && (
                          <span className="row-meta id-text">
                            {row.metadata.error_code}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title={
                Object.values(filters).some(Boolean)
                  ? "ไม่มี log ตามตัวกรองนี้"
                  : "ยังไม่มีบันทึกการทำงาน"
              }
              description="กิจกรรมการทดสอบและข้อผิดพลาดจะแสดงที่นี่ ลองเปลี่ยนตัวกรองหรือเริ่มทดสอบ OCR"
            />
          ))
        )}
      </section>
      <div className="table-footer">
        <span>
          {total ? offset + 1 : 0}–{Math.min(offset + 25, total)} / {total}{" "}
          รายการ
        </span>
        <div>
          <button
            className="button secondary"
            disabled={!offset || loading}
            onClick={() => setOffset((n) => Math.max(0, n - 25))}
          >
            ก่อนหน้า
          </button>
          <button
            className="button secondary"
            disabled={offset + 25 >= total || loading}
            onClick={() => setOffset((n) => n + 25)}
          >
            ถัดไป
          </button>
        </div>
      </div>
      <p className="filter-note">
        แสดงเฉพาะสถานะและรหัสอ้างอิง ไม่แสดงข้อความ OCR, Ground Truth, ภาพ
        หรือข้อมูลลับ
      </p>
    </div>
  );
}
