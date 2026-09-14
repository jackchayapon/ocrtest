"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { RefreshCw, Plus } from "lucide-react";
import { getHistory, getCategories, getPipelines } from "@/lib/api";
import { categoryLabel, t, userError, pipelineLabel } from "@/lib/i18n/th";
import type { TestCase, Category, PipelineConfig, QueryFilters } from "@/types";
import {
  PageHeader,
  FilterBar,
  DatasetFilters,
  CaseStatus,
  caseState,
  LoadingState,
  EmptyState,
} from "@/components/ConsoleUI";
import DeleteHistoryButton from "@/components/DeleteHistoryButton";
import { percent } from "@/components/MatrixTable";
export default function HistoryPage() {
  const router = useRouter();
  const [cases, setCases] = useState<TestCase[]>([]),
    [categories, setCategories] = useState<Category[]>([]),
    [pipelines, setPipelines] = useState<PipelineConfig[]>([]);
  const [filters, setFilters] = useState<QueryFilters>({}),
    [search, setSearch] = useState(""),
    [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0),
    [hasNext, setHasNext] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [revision, setRevision] = useState(0);
  const invalid = !!(
    filters.date_from &&
    filters.date_to &&
    filters.date_from > filters.date_to
  );
  useEffect(() => {
    async function restoreFilters() {
      const q = new URLSearchParams(window.location.search);
      if (q.get("category") || q.get("document"))
        setFilters({
          category: q.get("category") || undefined,
          document: q.get("document") || undefined,
        });
    }
    void restoreFilters();
  }, []);
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
        getHistory({ ...filters, limit: 21, offset }),
        getCategories(),
        getPipelines(),
      ])
        .then(([h, c, p]) => {
          if (active) {
            setCases(h.slice(0, 20));
            setHasNext(h.length > 20);
            setCategories(c);
            setPipelines(p);
          }
        })
        .catch((e) => {
          if (active)
            setError(userError(e.message) || "ไม่สามารถโหลดประวัติได้");
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
  function filter(k: keyof QueryFilters, v: string) {
    setOffset(0);
    setFilters((old) => ({ ...old, [k]: v || undefined }));
  }
  const visible = cases.filter(
    (c) =>
      (!search ||
        c.document.filename
          .toLocaleLowerCase()
          .includes(search.toLocaleLowerCase())) &&
      (!status || caseState(c).code === status),
  );
  return (
    <div className="page-stack">
      <PageHeader
        title="ประวัติการทดสอบ"
        description="ค้นหาเอกสาร เปิดผลล่าสุด และจัดการชุดทดสอบที่บันทึกไว้"
        actions={
          <>
            <button
              className="button secondary"
              aria-label={t("Refresh history")}
              disabled={loading}
              onClick={() => setRevision((n) => n + 1)}
            >
              <RefreshCw size={16} />
            </button>
            <Link className="button primary" href="/">
              <Plus size={16} />
              เริ่มทดสอบใหม่
            </Link>
          </>
        }
      />
      <FilterBar
        count={
          Object.values(filters).filter(Boolean).length +
          Number(!!search) +
          Number(!!status)
        }
        onClear={() => {
          setFilters({});
          setSearch("");
          setStatus("");
          setOffset(0);
        }}
      >
        <label className="field filter-search">
          ค้นหาในรายการหน้านี้
          <input
            className="input"
            placeholder="ชื่อเอกสาร"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <DatasetFilters
          value={filters}
          categories={categories}
          pipelines={pipelines}
          onChange={filter}
        />
        <label className="field">
          สถานะในหน้านี้
          <select
            className="select"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">ทุกสถานะ</option>
            <option value="success">สำเร็จ</option>
            <option value="partial">บาง Pipeline ผิดพลาด</option>
            <option value="error">ผิดพลาด</option>
            <option value="no_gt">รอ Ground Truth</option>
            <option value="pending">รอดำเนินการ</option>
          </select>
        </label>
      </FilterBar>
      {filters.document && (
        <p className="filter-note">
          กำลังกรองเอกสาร <code>{filters.document}</code>
        </p>
      )}
      {invalid && (
        <p className="error-banner" role="alert">
          วันที่สิ้นสุดต้องไม่อยู่ก่อนวันเริ่มต้น
        </p>
      )}
      {error && (
        <div className="error-banner" role="alert">
          ไม่สามารถโหลดประวัติได้: {error}{" "}
          <button
            className="button small"
            onClick={() => setRevision((n) => n + 1)}
          >
            ลองใหม่
          </button>
        </div>
      )}
      <section className="panel">
        {loading ? (
          <LoadingState label="กำลังโหลดประวัติ…" />
        ) : (
          !error &&
          !invalid &&
          (visible.length ? (
            <div
              className="table-wrap"
              tabIndex={0}
              role="region"
              aria-label="ตารางข้อมูล เลื่อนแนวนอนเพื่อดูคอลัมน์เพิ่มเติม"
            >
              <table className="data-table" style={{ minWidth: 960 }}>
                <caption className="sr-only">
                  ประวัติการทดสอบและผลล่าสุด เปิดเอกสารเพื่อดูรายละเอียด
                </caption>
                <thead>
                  <tr>
                    {[
                      "เอกสาร / หน้า",
                      "วันที่",
                      "ประเภทข้อมูล",
                      "สถานะ",
                      "ผลล่าสุดตาม Pipeline",
                      "การทำงาน",
                    ].map((h) => (
                      <th key={h} scope="col">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visible.map((c) => (
                    <tr
                      key={c.id}
                      data-href={`/test/${c.id}`}
                      onClick={(e) => {
                        if (
                          !(e.target as HTMLElement).closest(
                            "a,button,input,select,summary,[role=alertdialog]",
                          )
                        )
                          router.push(`/test/${c.id}`);
                      }}
                    >
                      <td>
                        <Link className="row-title" href={`/test/${c.id}`}>
                          {c.document.filename}
                        </Link>
                        <span className="row-meta">
                          หน้า {c.page_number ?? 1} / {c.document.page_count}
                        </span>
                        <span className="row-meta">
                          {c.ground_truth_raw === null
                            ? "ยังไม่มี Ground Truth"
                            : "มี Ground Truth"}
                        </span>
                      </td>
                      <td>
                        <time dateTime={c.created_at}>
                          {new Date(c.created_at).toLocaleDateString("th-TH")}
                        </time>
                      </td>
                      <td>
                        <div className="row-tags">
                          {c.categories.length
                            ? c.categories.map((cat) => (
                                <span className="badge neutral" key={cat.code}>
                                  {categoryLabel(cat)}
                                </span>
                              ))
                            : "—"}
                        </div>
                      </td>
                      <td>
                        <CaseStatus record={c} />
                      </td>
                      <td>
                        {pipelines.map((p) => {
                          const r = [...c.runs]
                            .reverse()
                            .find((r) => r.pipeline_id === p.pipeline_id);
                          return (
                            <div
                              key={p.pipeline_id}
                              className="flex justify-between gap-5"
                            >
                              <span>
                                {pipelineLabel(p.pipeline_id, p.name)}
                              </span>
                              <span>
                                {!r ? (
                                  "ยังไม่ทดสอบ"
                                ) : r.status === "error" ? (
                                  <span className="text-red-700">ผิดพลาด</span>
                                ) : (
                                  <>CER {percent(r.metrics?.cer)}</>
                                )}
                              </span>
                            </div>
                          );
                        })}
                      </td>
                      <td>
                        <div className="row-actions">
                          <Link className="button small" href={`/test/${c.id}`}>
                            เปิด
                          </Link>
                          <Link
                            className="button small"
                            href={`/logs?test_case_id=${c.id}`}
                          >
                            ดู Log
                          </Link>
                          <DeleteHistoryButton
                            id={c.id}
                            onDeleted={() => setRevision((n) => n + 1)}
                          />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title={
                cases.length
                  ? "ไม่พบประวัติตามตัวกรองนี้"
                  : "ยังไม่มีประวัติการทดสอบ"
              }
              description="ผล OCR และข้อความอ้างอิงที่บันทึกจะปรากฏที่นี่ เพื่อเปิดตรวจและเปรียบเทียบได้ภายหลัง"
              action={
                <Link className="button primary" href="/">
                  เริ่มทดสอบ OCR
                </Link>
              }
            />
          ))
        )}
      </section>
      <div className="table-footer">
        <span>
          {visible.length} รายการในหน้านี้ · หน้า {offset / 20 + 1}
        </span>
        <div>
          <button
            className="button secondary"
            disabled={!offset || loading}
            onClick={() => setOffset((n) => Math.max(0, n - 20))}
          >
            ก่อนหน้า
          </button>
          <button
            className="button secondary"
            disabled={!hasNext || loading}
            onClick={() => setOffset((n) => n + 20)}
          >
            ถัดไป
          </button>
        </div>
      </div>
    </div>
  );
}
