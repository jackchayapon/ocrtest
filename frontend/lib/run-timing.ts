import type { PipelineRun } from "@/types";

export function runTimingText(run: Pick<PipelineRun, "timing_semantics" | "wall_time_ms" | "total_field_compute_ms" | "processing_time_ms">): string {
  if (run.timing_semantics === "wall_clock_v1" && run.wall_time_ms != null) {
    return `เวลาที่ผ่านไปจริง ${run.wall_time_ms} ms · ผลรวมเวลา Fields ${run.total_field_compute_ms ?? "—"} ms`;
  }
  return `เวลาที่บันทึก ${run.processing_time_ms ?? "—"} ms · ประวัติ Global รุ่นเก่าอาจเป็นผลรวมเวลา Fields`;
}
