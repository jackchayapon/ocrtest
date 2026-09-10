import { t } from "@/lib/i18n/th";
import type { Metadata } from "next";
import AppShell from "@/components/AppShell";
import "./globals.css";

export const metadata: Metadata = { title: t("OCR Lab · Testing & Benchmark"), description: t("A workspace for comparing OCR pipelines, reviewing ground truth, and measuring recognition quality.") };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="th"><body><AppShell>{children}</AppShell></body></html>;
}
