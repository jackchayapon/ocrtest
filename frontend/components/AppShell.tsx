"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  BarChart3,
  BookOpen,
  FlaskConical,
  History,
  Layers3,
  Menu,
  ScanLine,
  Settings2,
  X,
} from "lucide-react";
const links = [
  { href: "/", label: "ทดสอบ OCR", icon: FlaskConical },
  { href: "/history", label: "ประวัติ", icon: History },
  { href: "/matrix", label: "เปรียบเทียบ", icon: BarChart3 },
  { href: "/analytics/categories", label: "วิเคราะห์", icon: Layers3 },
  { href: "/logs", label: "บันทึกระบบ", icon: BookOpen },
];
export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const detail = pathname.startsWith("/test/");
  const section =
    links.find((l) => l.href === pathname)?.label ??
    (detail ? "รายละเอียดชุดทดสอบ" : "ตั้งค่า Pipeline");
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        ข้ามไปเนื้อหา
      </a>
      <aside className={`sidebar ${open ? "nav-open" : ""}`}>
        <div className="brand-row">
          <Link href="/" className="brand" onClick={() => setOpen(false)}>
            <ScanLine size={24} />
            <span>
              OCR<span className="brand-light">Lab</span>
            </span>
          </Link>
          <button
            className="button ghost mobile-menu"
            aria-label={open ? "ปิดเมนู" : "เปิดเมนู"}
            aria-expanded={open}
            aria-controls="console-navigation"
            onClick={() => setOpen(!open)}
          >
            {open ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
        <nav id="console-navigation" aria-label="เมนูหลัก">
          <div className="workspace-label">งานหลัก</div>
          {links.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || (href === "/history" && detail);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                onClick={() => setOpen(false)}
                className={`nav-link ${active ? "active" : ""}`}
              >
                <Icon size={18} />
                {label}
              </Link>
            );
          })}
          <div className="sidebar-divider" />
          <div className="workspace-label">การตั้งค่า</div>
          <Link
            href="/settings/pipelines"
            aria-current={
              pathname === "/settings/pipelines" ? "page" : undefined
            }
            className={`nav-link ${pathname === "/settings/pipelines" ? "active" : ""}`}
            onClick={() => setOpen(false)}
          >
            <Settings2 size={18} />
            Pipeline
          </Link>
        </nav>
        <div className="sidebar-footer">
          <span className="muted">OCR Evaluation Console</span>
        </div>
      </aside>
      <div className="main-shell">
        <div className="topbar">
          <nav aria-label="ตำแหน่งปัจจุบัน">
            <span className="muted">OCRLab</span>
            <span className="breadcrumb-slash">/</span>
            {detail && (
              <>
                <Link href="/history">ประวัติ</Link>
                <span className="breadcrumb-slash">/</span>
              </>
            )}
            <strong>{section}</strong>
          </nav>
        </div>
        <main id="main-content">{children}</main>
      </div>
    </div>
  );
}
