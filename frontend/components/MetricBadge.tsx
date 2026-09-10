export function percent(value: number | null | undefined): string { return value == null ? "—" : `${(value * 100).toFixed(1)}%`; }

export default function MetricBadge({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return <div className={`metric-item ${good ? "good" : ""}`} title={metricHelp[label]}><small>{label}</small><strong>{value}</strong></div>;
}
import { metricHelp } from "@/lib/i18n/th";
