import Link from "next/link";
import { FileSearch, Loader2, SlidersHorizontal } from "lucide-react";
import type { ReactNode } from "react";
import type { Category, PipelineConfig, QueryFilters, TestCase } from "@/types";
import { categoryLabel, pipelineLabel } from "@/lib/i18n/th";
export function PageHeader({
  title,
  description,
  actions,
  back,
}: {
  title: string;
  description: string;
  actions?: ReactNode;
  back?: { href: string; label: string };
}) {
  return (
    <header className="page-heading console-heading">
      <div>
        {back && (
          <Link className="mini-link" href={back.href}>
            ← {back.label}
          </Link>
        )}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state console-empty">
      <FileSearch size={28} aria-hidden="true" />
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function LoadingState({ label }: { label: string }) {
  return (
    <div className="loading-state" role="status">
      <Loader2 size={18} className="busy-spinner" />
      {label}
    </div>
  );
}
export function FilterBar({
  count,
  onClear,
  children,
}: {
  count: number;
  onClear: () => void;
  children: ReactNode;
}) {
  return (
    <section className="panel console-filters" aria-label="ตัวกรอง">
      <div className="filter-heading">
        <span>
          <SlidersHorizontal size={16} /> ตัวกรอง{" "}
          {count > 0 && <span className="badge">{count}</span>}
        </span>
        <button
          className="button small ghost"
          disabled={!count}
          onClick={onClear}
        >
          ล้างตัวกรอง
        </button>
      </div>
      <div className="filter-fields">{children}</div>
    </section>
  );
}
export function DatasetFilters({
  value,
  categories,
  pipelines,
  onChange,
}: {
  value: QueryFilters;
  categories: Category[];
  pipelines?: PipelineConfig[];
  onChange: (key: keyof QueryFilters, value: string) => void;
}) {
  return (
    <>
      <label className="field">
        ประเภทข้อมูล
        <select
          aria-label="ประเภทข้อมูล"
          className="select"
          value={value.category || ""}
          onChange={(e) => onChange("category", e.target.value)}
        >
          <option value="">ทุกประเภทข้อมูล</option>
          {categories.map((c) => (
            <option key={c.id} value={c.code}>
              {categoryLabel(c)}
            </option>
          ))}
        </select>
      </label>
      {pipelines && (
        <label className="field">
          Pipeline
          <select
            aria-label="Pipeline"
            className="select"
            value={value.pipeline || ""}
            onChange={(e) => onChange("pipeline", e.target.value)}
          >
            <option value="">ทุก Pipeline</option>
            {pipelines.map((p) => (
              <option key={p.pipeline_id} value={p.pipeline_id}>
                {pipelineLabel(p.pipeline_id, p.name)}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="field">
        ตั้งแต่วันที่
        <input
          className="input"
          type="date"
          value={value.date_from || ""}
          onChange={(e) => onChange("date_from", e.target.value)}
        />
      </label>
      <label className="field">
        ถึงวันที่
        <input
          className="input"
          type="date"
          min={value.date_from}
          value={value.date_to || ""}
          onChange={(e) => onChange("date_to", e.target.value)}
        />
      </label>
    </>
  );
}
export function caseState(record: TestCase) {
  const latest = Object.values(
    Object.fromEntries(record.runs.map((r) => [r.pipeline_id, r])),
  );
  if (!latest.length)
    return { label: "รอดำเนินการ", tone: "neutral", code: "pending" };
  const failures = latest.filter((r) => r.status === "error").length;
  if (failures)
    return {
      label: failures === latest.length ? "ผิดพลาด" : "บาง Pipeline ผิดพลาด",
      tone: failures === latest.length ? "error" : "warning",
      code: failures === latest.length ? "error" : "partial",
    };
  if (record.ground_truth_raw === null)
    return { label: "รอ Ground Truth", tone: "warning", code: "no_gt" };
  return { label: "สำเร็จ", tone: "success", code: "success" };
}
export function CaseStatus({ record }: { record: TestCase }) {
  const s = caseState(record);
  return <span className={`badge ${s.tone}`}>{s.label}</span>;
}
export function Stat({
  label,
  value,
  note,
}: {
  label: string;
  value: ReactNode;
  note?: string;
}) {
  return (
    <div className="stat-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <p>{note}</p>}
    </div>
  );
}
