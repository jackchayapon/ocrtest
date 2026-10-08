"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { RefreshCw, Plus } from "lucide-react";
import { getHistory, getAnalyticsPipelines, bulkDeleteTestCases } from "@/lib/api";
import { useAnalyticsFilters } from "@/lib/analytics-scope";
import AnalyticsFilters from "@/components/AnalyticsFilters";
import { t, userError, pipelineLabel } from "@/lib/i18n/th";
import type { TestCase, AnalyticsPipeline, QueryFilters } from "@/types";
import {
  PageHeader,
  FilterBar,
  CaseStatus,
  caseState,
  LoadingState,
  EmptyState,
} from "@/components/ConsoleUI";
import BulkConfirm from "@/components/BulkConfirm";
import {useManagedSelection} from "@/lib/bulk-selection";
import DeleteHistoryButton from "@/components/DeleteHistoryButton";
import { percent } from "@/components/MatrixTable";
export default function HistoryPage() {
  const router = useRouter();
  const [cases, setCases] = useState<TestCase[]>([]),
    [pipelines, setPipelines] = useState<AnalyticsPipeline[]>([]);
  const [filters, setFilters] = useAnalyticsFilters();
  const [search, setSearch] = useState(""),
    [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0),
    [hasNext, setHasNext] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [revision, setRevision] = useState(0);
  const selection=useManagedSelection<string>(JSON.stringify([filters,search,status]), id=>id);
  const [notice,setNotice]=useState("");
  const invalid = !!(
    filters.date_from &&
    filters.date_to &&
    filters.date_from > filters.date_to
  );
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError("");
      if (invalid) {
        setLoading(false);
        return;
      }
      await Promise.all([
        getHistory({ ...filters, limit: 21, offset }, controller.signal),
        getAnalyticsPipelines(controller.signal),
      ])
        .then(([h, p]) => {
          if (active) {
            setCases(h.slice(0, 20));
            setHasNext(h.length > 20);
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
      controller.abort();
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
            <Link className="button secondary" href="/matrix">เปรียบเทียบผล</Link>
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
          ค้นหาในหน้านี้
          <input
            className="input"
            placeholder="ชื่อเอกสาร"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <AnalyticsFilters
          value={filters}
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
      {notice&&<p className="notice-banner" role="status">{notice}</p>}
      {<section className="panel panel-body flex flex-wrap items-center gap-3" aria-label="จัดการประวัติที่เลือก"><strong>เลือกแล้ว {selection.items.length} รายการ</strong><button className="button secondary" disabled={!selection.items.length} onClick={selection.clear}>ล้างการเลือก</button><BulkConfirm count={selection.items.length} kind="history" onConfirm={async()=>{const r=await bulkDeleteTestCases(selection.items);selection.clear();setNotice(`ลบประวัติ ${r.deleted} รายการแล้ว${r.already_missing?` · ไม่พบแล้ว ${r.already_missing} รายการ`:""}`);setRevision(v=>v+1);}}/></section>}
      <p className="filter-note">เลือกได้สูงสุด 200 รายการ รวมทุกหน้า · เปลี่ยนตัวกรองจะล้างการเลือก</p>
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
                    <th><input type="checkbox" aria-label="เลือกประวัติที่เห็นในหน้านี้ทั้งหมด" checked={selection.all(visible.map(c=>c.id))} onChange={()=>selection.page(visible.map(c=>c.id))}/></th>
                    {[
                      "เอกสาร / หน้า",
                      "วันที่สร้าง",
                      "ประเภทเอกสาร",
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
                      <td><input type="checkbox" aria-label={`เลือกประวัติ ${c.id}`} checked={selection.has(c.id)} disabled={!selection.has(c.id)&&selection.items.length>=200} onChange={()=>selection.toggle(c.id)}/></td>
                      <td>
                        <Link className="row-title" href={`/test/${c.id}`}>
                          {c.document.filename}
                        </Link>
                        <span className="row-meta">
                          หน้า {c.page_number ?? 1} / {c.document.page_count}
                        </span>
                        <span className="row-meta">
                          {c.workflow === "global" ? `${c.global_fields?.length ?? 0} Fields · GT ยืนยัน ${c.global_fields?.filter(f=>f.confirmed_at).length ?? 0}` : c.ground_truth_raw === null
                            ? "ยังไม่มี Ground Truth"
                            : "มี Ground Truth"}
                        </span>
                      </td>
                      <td>
                        <time dateTime={c.created_at}>
                          {new Date(c.created_at).toLocaleDateString("th-TH", {timeZone:"UTC"})}
                        </time>
                      </td>
                      <td>
                        {c.document.document_type_name || "ไม่ระบุประเภท"}
                      </td>
                      <td>
                        <CaseStatus record={c} />
                      </td>
                      <td>
                        {pipelines.filter(p => c.runs.some(r => r.pipeline_id === p.pipeline_id)).map((p) => {
                          const r = [...c.runs]
                            .reverse()
                            .find((r) => r.pipeline_id === p.pipeline_id);
                          return (
                            <div
                              key={p.pipeline_id}
                              className="flex justify-between gap-5"
                            >
                              <span>
                                {pipelineLabel(p.pipeline_id, p.pipeline_name)}{p.retired && <span className="badge neutral">เก็บถาวร</span>}
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
