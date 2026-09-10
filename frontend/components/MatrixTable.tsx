import { pipelineLabel, t } from "@/lib/i18n/th";
import { ArrowDown, ArrowUp, CircleHelp } from "lucide-react";
import type { MatrixRow } from "@/types";

export function percent(value: number | null | undefined, digits = 1) {
  return value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

export default function MatrixTable({ rows }: { rows: MatrixRow[] }) {
  const measured = rows.filter((row) => row.cer != null);
  const bestCer = measured.length ? Math.min(...measured.map((row) => row.cer!)) : null;

  return (
    <div className="table-wrap">
      <table className="data-table min-w-[920px]">
        <caption className="sr-only">{t("Latest result per test case and pipeline. Lower CER, WER, and time are better.")}</caption>
        <thead>
          <tr>
            <th scope="col">Pipeline</th>
            <th scope="col">{t("Tests")}</th>
            <th scope="col">{t("Evaluated")}</th>
            <th scope="col"><span className="inline-flex items-center gap-1">{t("Mean CER")} <ArrowDown size={12} /></span></th>
            <th scope="col"><span className="inline-flex items-center gap-1">{t("Mean WER")} <ArrowDown size={12} /></span></th>
            <th scope="col"><span className="inline-flex items-center gap-1">{t("Exact match")} <ArrowUp size={12} /></span></th>
            <th scope="col">{t("Avg. time")}</th>
            <th scope="col">{t("Avg. Gateway time")}</th>
            <th scope="col">{t("Confidence")}</th>
            <th scope="col">{t("Failures")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.pipeline_id}>
              <td>
                <div className="flex items-center gap-3">
                  <span className={`h-8 w-1 rounded-full ${["bg-indigo-500", "bg-teal-500", "bg-violet-500"][index % 3]}`} />
                  <div><span className="font-semibold text-slate-800">{pipelineLabel(row.pipeline_id, row.pipeline_name)}</span><span className="block pt-1 text-[11px] text-slate-400">{row.pipeline_id}</span></div>
                </div>
              </td>
              <td className="tabular-nums">{row.tests}</td>
              <td className="tabular-nums">{row.evaluated_runs}</td>
              <td className="tabular-nums"><span className={row.cer != null && row.cer === bestCer ? "rounded-md bg-emerald-50 px-2 py-1 font-semibold text-emerald-700" : "font-medium"}>{percent(row.cer)}</span></td>
              <td className="tabular-nums">{percent(row.wer)}</td>
              <td className="tabular-nums">{percent(row.exact_match_rate)}</td>
              <td className="whitespace-nowrap tabular-nums">{row.avg_time_ms == null ? "—" : `${Math.round(row.avg_time_ms).toLocaleString()} ms`}</td>
              <td className="whitespace-nowrap tabular-nums">{row.avg_gateway_time_ms == null ? "—" : `${Math.round(row.avg_gateway_time_ms).toLocaleString()} ms`}</td>
              <td className="tabular-nums">{percent(row.avg_confidence)}</td>
              <td><span className={row.failed_runs ? "font-medium text-rose-600" : "text-slate-400"}>{row.failed_runs}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <div className="empty-state py-16">{t("No pipeline results match these filters.")}</div>}
      <div className="flex items-start gap-2 border-t border-slate-100 px-5 py-4 text-xs leading-relaxed text-slate-500"><CircleHelp size={15} className="mt-0.5 shrink-0" /><span>{t("Each test case contributes its latest run for each pipeline. Error rates and exact match average only successful runs with ground truth. Missing confidence is excluded from its average.")}</span></div>
    </div>
  );
}
