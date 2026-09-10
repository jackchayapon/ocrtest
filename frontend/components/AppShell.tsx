"use client";
import { t } from "@/lib/i18n/th";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowUpRight, BarChart3, BookOpen, FlaskConical, History, Layers3, ScanLine, Settings2 } from "lucide-react";

const links = [
  { href: "/", label: t("Testing workspace"), icon: FlaskConical },
  { href: "/history", label: t("Test history"), icon: History },
  { href: "/matrix", label: t("Benchmark matrix"), icon: BarChart3 },
  { href: "/analytics/categories", label: t("Category analysis"), icon: Layers3 },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return <div className="app-shell">
    <aside className="sidebar">
      <Link href="/" className="brand"><span className="brand-icon"><ScanLine size={23} /></span><span>OCR<span className="brand-light">Lab</span><small>{t("TESTING & BENCHMARK")}</small></span></Link>
      <div className="workspace-label">{t("WORKSPACE")}</div>
      <nav aria-label={t("Main navigation")}>{links.map(({ href, label, icon: Icon }) => <Link href={href} key={href} className={`nav-link ${pathname === href ? "active" : ""}`}><Icon size={18} /><span>{label}</span>{pathname === href && <span className="nav-dot" />}</Link>)}</nav>
      <div className="sidebar-divider" />
      <div className="workspace-label">{t("MANAGE")}</div>
      <Link href="/settings/pipelines" className={`nav-link ${pathname === "/settings/pipelines" ? "active" : ""}`}><Settings2 size={18} />{t("Pipeline settings")}</Link>
      <div className="sidebar-footer"><div className="sidebar-note"><BookOpen size={19} /><strong>{t("Built for better OCR")}</strong><p>{t("One test case. Three pipelines.")}<br />{t("A clearer comparison.")}</p><Link href="/matrix">{t("Explore benchmarks")} <ArrowUpRight size={14} /></Link></div><span className="version"><span /> {t("OCR Testing App")} <span className="version-number">v0.1</span></span></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div><span className="muted">{t("Workspace")}</span><span className="breadcrumb-slash">/</span><strong>{links.find(l => l.href === pathname)?.label ?? (pathname.startsWith("/test/") ? t("Test detail") : t("Pipeline settings"))}</strong></div><div className="topbar-end"><span className="badge neutral">{t("BENCHMARK WORKSPACE")}</span><span className="avatar">OC</span></div></header><main>{children}</main><footer className="main-footer">{t("OCR Testing & Benchmark App")}<span>{t("Measure. Compare. Improve.")}</span></footer></div>
  </div>;
}
