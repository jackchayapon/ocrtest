"use client";
import { useState } from "react";
import { deleteTestCase } from "@/lib/api";

export default function DeleteHistoryButton({ id, onDeleted }: { id: string; onDeleted: () => void }) {
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function remove() {
    setBusy(true); setError("");
    try { await deleteTestCase(id); setOpen(false); onDeleted(); }
    catch { setError("ลบประวัติไม่สำเร็จ กรุณาลองใหม่"); }
    finally { setBusy(false); }
  }
  return <><button className="button small text-red-600" onClick={() => setOpen(true)}>ลบประวัติ</button>{open && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"><section role="alertdialog" aria-modal="true" aria-labelledby={`delete-${id}`} className="panel max-w-md p-6"><h2 id={`delete-${id}`} className="font-semibold">ต้องการลบประวัติการทดสอบนี้หรือไม่?</h2><p className="my-4">ผล OCR, metrics และ Ground Truth ของชุดทดสอบนี้จะถูกลบ เอกสารต้นฉบับและผลหน้าอื่นยังคงอยู่</p><div className="flex gap-3"><button autoFocus className="button secondary" disabled={busy} onClick={() => setOpen(false)}>ยกเลิก</button><button className="button primary" disabled={busy} onClick={() => void remove()}>ยืนยันลบประวัติ</button></div>{error && <p role="alert">{error}</p>}</section></div>}</>;
}
