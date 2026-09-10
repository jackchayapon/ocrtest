"use client";
import { t } from "@/lib/i18n/th";
import { useRef } from "react";
import { Upload } from "lucide-react";

export default function DocumentUploader({ onUpload, disabled, label = t("Upload document"), primary = false }: { onUpload: (file: File) => void; disabled?: boolean; label?: string; primary?: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  return <><input aria-label={t("Upload document file")} className="sr-only" ref={ref} type="file" accept="application/pdf,.pdf,image/png,image/jpeg,image/webp,image/tiff,image/bmp" disabled={disabled} onChange={event => { const file = event.target.files?.[0]; if (file) onUpload(file); event.target.value = ""; }} /><button className={`button ${primary ? "primary" : "secondary"}`} disabled={disabled} onClick={() => ref.current?.click()}><Upload size={14} />{label}</button></>;
}
