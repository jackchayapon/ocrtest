import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";

const api = process.env.E2E_API_URL || "http://127.0.0.1:8100";
for (const populated of ["subfields", "whole"] as const) {
  test(`recover saved GT when only ${populated} has text`, async ({ page, request }) => {
    const upload = await request.post(`${api}/api/documents`, { multipart: { file: {
      name: "synthetic-gt-recovery.png", mimeType: "image/png",
      buffer: fs.readFileSync(path.resolve("public/sample-document.png")),
    } } });
    expect(upload.status()).toBe(201);
    const doc = await upload.json();
    const created = await request.post(`${api}/api/test-cases`, { data: { workflow: "global", document_id: doc.id } });
    const record = await created.json(), fid = randomUUID();
    const layout = await request.put(`${api}/api/test-cases/${record.id}/global-fields`, { data: {
      confirmed: true, fields: [{ id: fid, field_index: 1, source: "manual", roi: { x1: 20, y1: 20, x2: 700, y2: 180 } }],
    } });
    expect(layout.status()).toBe(200);
    const pipeline = await request.post(`${api}/api/pipelines`, { data: { name: "GT Recovery " + randomUUID(), source: "custom", execution_mode: "integrated", version: "6", det_weight: "baseline", rec_weight: "baseline" } });
    const p = await pipeline.json();
    const run = await request.post(`${api}/api/test-cases/${record.id}/run`, { data: { pipelines: [p.pipeline_id] } });
    expect(run.status()).toBe(200);
    const text = "ข้อความสังเคราะห์ 123";
    await request.put(`${api}/api/test-cases/${record.id}/global-fields/${fid}/ground-truth`, { data: { ground_truth_raw: populated === "subfields" ? text : "" } });
    await request.put(`${api}/api/test-cases/${record.id}/ground-truth`, { data: { ground_truth_raw: populated === "whole" ? text : "", confirmed: false } });
    await page.goto(`/workflow/${record.id}/ground-truth?edit=1`);
    const whole = page.getByRole("button", { name: "ใช้ข้อความ Whole Field", exact: true });
    const fields = page.getByRole("button", { name: "ใช้ข้อความ Sub-fields", exact: true });
    await expect(populated === "whole" ? fields : whole).toBeDisabled();
    const useSaved = populated === "whole" ? whole : fields;
    await expect(useSaved).toBeEnabled();await useSaved.click();
    const confirm = page.getByRole("button", { name: "ยืนยันเพื่อคำนวณ", exact: true });
    await expect(confirm).toBeEnabled();
    const response = page.waitForResponse(r => r.url().endsWith("/evaluate") && r.request().method() === "POST");
    await confirm.click();expect((await response).status()).toBe(200);
    const saved = await (await request.get(`${api}/api/test-cases/${record.id}`)).json();
    expect(saved.ground_truth_raw).toBe(text);expect(saved.global_fields[0].ground_truth_raw).toBe(text);
    expect(saved.runs[0].fields[0].evaluation).toBeTruthy();
    await expect(page.getByTestId("run-timing")).toContainText("เวลาที่ผ่านไปจริง");
    expect(saved.runs[0].processing_time_ms).toBe(saved.runs[0].wall_time_ms);
  });
}
