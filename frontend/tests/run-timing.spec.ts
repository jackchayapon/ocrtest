import { expect, test } from "@playwright/test";
import { runTimingText } from "../lib/run-timing";

test("new global timing separates elapsed time and summed field compute", () => {
  const text = runTimingText({timing_semantics:"wall_clock_v1",wall_time_ms:1200,total_field_compute_ms:3600,processing_time_ms:1200});
  expect(text).toContain("เวลาที่ผ่านไปจริง 1200 ms");
  expect(text).toContain("ผลรวมเวลา Fields 3600 ms");
});

test("historical values are not relabeled as measured wall time", () => {
  const text=runTimingText({timing_semantics:"legacy_recorded",processing_time_ms:9000});
  expect(text).toContain("เวลาที่บันทึก 9000 ms");
  expect(text).not.toContain("เวลาที่ผ่านไปจริง");
});

test("summary and absent historical timing remain honest", () => {
  expect(runTimingText({timing_semantics:"not_loaded",processing_time_ms:null})).toContain("เวลาที่บันทึก — ms");
});
