"use client";
import { useState } from "react";
import Link from "next/link";
import { createPortal } from "react-dom";
import { runPages, type PageProgress } from "@/lib/api";

export function parsePages(input: string, count: number): number[] {
  const pages = new Set<number>();
  for (const part of input
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)) {
    const match = /^(\d+)(?:\s*-\s*(\d+))?$/.exec(part);
    if (!match) throw new Error("ระบุหน้าเช่น 1, 3, 5-8");
    const first = Number(match[1]),
      last = Number(match[2] ?? match[1]);
    if (first < 1 || last > count || first > last)
      throw new Error("หมายเลขหน้าไม่ถูกต้อง");
    for (let page = first; page <= last; page++) pages.add(page);
  }
  return [...pages].sort((a, b) => a - b);
}

export default function PdfBatchPanel({
  documentId,
  pageCount,
  pipelines,
  categoryCodes,
  disabled,
  onBusy,
  activePage,
  onPreview,
  onReview,
  runTarget,
}: {
  documentId: string;
  pageCount: number;
  pipelines: string[];
  categoryCodes: string[];
  disabled: boolean;
  onBusy: (busy: boolean) => void;
  activePage: number;
  onPreview: (page: number) => void;
  onReview: (id: string) => void;
  runTarget: HTMLDivElement | null;
}) {
  const [selection, setSelection] = useState("");
  const [railOffset, setRailOffset] = useState(0);
  const [states, setStates] = useState<Record<number, PageProgress>>({});
  const [running, setRunning] = useState(false),
    [error, setError] = useState("");
  let pages: number[] = [],
    invalid = "";
  try {
    pages = parsePages(selection, pageCount);
  } catch (e) {
    invalid = (e as Error).message;
  }
  async function start(selected: number[]) {
    if (running || !selected.length) return;
    setRunning(true);
    onBusy(true);
    setError("");
    setStates((old) => ({
      ...old,
      ...Object.fromEntries(
        selected.map((page) => [
          page,
          { page, event: "queued", status: "queued" },
        ]),
      ),
    }));
    try {
      await runPages(
        documentId,
        selected,
        pipelines,
        categoryCodes,
        (event) => {
          if (event.page)
            setStates((old) => ({ ...old, [event.page!]: event }));
        },
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
      onBusy(false);
    }
  }
  const rows = Object.values(states).sort((a, b) => a.page! - b.page!);
  const current = rows.find((row) => row.status === "running");
  const failed = rows
    .filter((row) => row.status === "error")
    .map((row) => row.page!);
  return (
    <section className="panel batch-panel" aria-label="เลือกหลายหน้า PDF">
      <h2 className="font-semibold">OCR หลายหน้าแบบทีละหน้า</h2>
      <p className="my-2 text-xs text-slate-500">
        สร้างชุดทดสอบใหม่แบบเต็มหน้า ไม่แก้ ROI หรือ Ground Truth เดิม
        คลิกหมายเลขหน้าเพื่อพรีวิว ติ๊กเลือกเพื่อเข้าชุดประมวลผล ใช้ Pipeline
        และประเภทข้อมูลที่เลือกด้านขวากับทุกหน้า ประเภทข้อมูลไม่ถูกส่งให้โมเดล
      </p>
      <details className="technical-panel">
        <summary>ระบุช่วงหน้า (ตัวเลือกเพิ่มเติม)</summary>
        <label className="field">
          เลือกหน้า เช่น 1, 3, 5-8
          <input
            className="input"
            aria-label="ช่วงหน้า PDF"
            value={selection}
            disabled={disabled || running}
            onChange={(e) => setSelection(e.target.value)}
          />
        </label>
      </details>
      <div className="my-2 flex flex-wrap gap-2">
        <button
          className="button small"
          disabled={disabled || running}
          onClick={() => setSelection(`1-${pageCount}`)}
        >
          เลือกทุกหน้า
        </button>
        <button
          className="button small"
          disabled={disabled || running}
          onClick={() => setSelection("")}
        >
          ล้างหน้า
        </button>
        <span>เลือกแล้ว {pages.length} หน้า</span>
      </div>
      <div className="batch-page-list">
        {Array.from(
          { length: Math.min(20, pageCount - railOffset) },
          (_, i) => railOffset + i + 1,
        ).map((page) => (
          <div
            key={page}
            className={`batch-page-card ${activePage === page ? "active" : ""}`}
          >
            <button
              className="button ghost"
              aria-label={`พรีวิวหน้า ${page}`}
              aria-current={activePage === page ? "page" : undefined}
              disabled={disabled || running}
              onClick={() => onPreview(page)}
            >
              หน้า {page}
            </button>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                aria-label={`เลือกหน้า ${page}`}
                disabled={disabled || running}
                checked={pages.includes(page)}
                onChange={(e) =>
                  setSelection(
                    (e.target.checked
                      ? [...pages, page]
                      : pages.filter((p) => p !== page)
                    )
                      .sort((a, b) => a - b)
                      .join(", "),
                  )
                }
              />
              เลือก
            </label>
          </div>
        ))}
      </div>
      <div className="table-footer">
        <span>
          แสดงหน้า {railOffset + 1}–{Math.min(railOffset + 20, pageCount)} /{" "}
          {pageCount}
        </span>
        <div>
          <button
            className="button small"
            disabled={railOffset === 0}
            onClick={() => setRailOffset((n) => Math.max(0, n - 20))}
          >
            ก่อนหน้า
          </button>
          <button
            className="button small"
            disabled={railOffset + 20 >= pageCount}
            onClick={() => setRailOffset((n) => n + 20)}
          >
            ถัดไป
          </button>
        </div>
      </div>
      {invalid && (
        <p role="alert" className="text-red-600">
          {invalid}
        </p>
      )}
      {runTarget &&
        createPortal(
          <div className="run-bar batch-run-bar">
            <div>
              <strong>
                {pages.length} หน้า · {pipelines.length} Pipeline
              </strong>
              <p>เต็มหน้า · แก้ Ground Truth แยกในผลแต่ละหน้า</p>
            </div>
            <button
              className="button primary"
              disabled={
                disabled ||
                running ||
                !!invalid ||
                !pages.length ||
                !pipelines.length
              }
              onClick={() => void start(pages)}
            >
              {running ? "กำลังประมวลผล…" : "ประมวลผลหน้าที่เลือก"}
            </button>
          </div>,
          runTarget,
        )}
      {current && (
        <p role="status">
          กำลังประมวลผลหน้า {current.page} (
          {rows.findIndex((r) => r.page === current.page) + 1} / {rows.length}{" "}
          หน้าที่เลือก)
        </p>
      )}
      <ul className="batch-progress" aria-live="polite">
        {rows.map((row) => (
          <li key={row.page}>
            หน้า {row.page} ·{" "}
            {
              (
                {
                  queued: "รอดำเนินการ",
                  running: "กำลังประมวลผล",
                  success: "สำเร็จ",
                  error: "ผิดพลาด",
                } as Record<string, string>
              )[row.status ?? "queued"]
            }{" "}
            {row.test_case_id && (
              <>
                <button
                  className="button small"
                  disabled={disabled || running}
                  onClick={() => onReview(row.test_case_id!)}
                >
                  ดูผลหน้า {row.page}
                </button>
                <Link
                  className="text-indigo-600 underline"
                  href={`/test/${row.test_case_id}`}
                >
                  เปิดผลและแก้ Ground Truth
                </Link>
              </>
            )}
          </li>
        ))}
      </ul>
      {!!failed.length && !running && (
        <button
          className="button secondary"
          disabled={disabled}
          onClick={() => void start(failed)}
        >
          ลองหน้าที่ผิดพลาดใหม่ (สร้างชุดทดสอบใหม่)
        </button>
      )}
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
    </section>
  );
}
