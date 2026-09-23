import { expect, test } from "@playwright/test";
import path from "node:path";
import { t } from "../lib/i18n/th";
import type { PipelineConfig, PipelineRun } from "../types";

const backend = process.env.E2E_API_URL || "http://127.0.0.1:8000";

test("Thai FT v2 fifth pipeline supports Auto/Manual ROI, field GT, persistence and dashboards", async ({ page, request }) => {
  const configs: PipelineConfig[] = await (await request.get(`${backend}/api/pipelines`)).json();
  expect(new Set(configs.map(p => p.pipeline_id))).toEqual(new Set(["mint", "hutch_crop", "hutch_full", "benchmark", "thai_ft_v2"]));
  await page.goto("/settings/pipelines");
  const card = page.locator("section").filter({ has: page.getByRole("heading", { name: "Thai FT v2", exact: true }) });
  await expect(card).toContainText("Recognition V6 + thai_ft_v2");
  await card.locator("summary").click();
  await expect(card.getByLabel(t("Image field"), { exact: true })).toHaveValue("images");
  for (const enabled of [false, true]) {
    expect((await request.put(`${backend}/api/pipelines/thai_ft_v2`, { data: { enabled } })).ok()).toBeTruthy();
  }
  await page.goto("/");
  await page.locator('input[type="file"]').first().setInputFiles(path.resolve("public/sample-document.png"));
  await expect(page.getByRole("button", { name: "ราย Field", exact: true })).toHaveAttribute("aria-pressed", "true");
  for (const config of configs) {
    const label = config.pipeline_id === "mint" ? t("Mint Custom") : config.name;
    const checkbox = page.getByLabel(`เลือก ${label}`, { exact: true });
    await expect(checkbox).toBeVisible();
    if (config.pipeline_id !== "thai_ft_v2") await checkbox.uncheck();
    else await checkbox.check();
  }
  await page.getByRole("button", { name: t("Auto Detect"), exact: true }).click();
  await page.getByRole("button", { name: "พื้นที่ 1", exact: true }).click();
  await expect(page.getByRole("button", { name: "พื้นที่ 2", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "ยืนยัน ROI", exact: true }).click();
  let pending = page.waitForResponse(r => r.url().endsWith("/run") && r.request().method() === "POST");
  await page.getByRole("button", { name: t("Run selected"), exact: true }).click();
  const result = await (await pending).json();
  expect(result.runs).toHaveLength(1);
  const run: PipelineRun = result.runs[0];
  expect(run).toMatchObject({ pipeline_id: "thai_ft_v2", status: "success", input_width: 770, input_height: 130 });
  await expect(page.getByTestId("result-text-thai_ft_v2")).toBeVisible();
  const field = page.getByTestId("ocr-field").first();
  await expect(field).toContainText("Confidence 97.00%");
  await field.getByRole("button", { name: "Field 01", exact: true }).click();
  await field.getByLabel("GT Field 1", { exact: true }).fill("ภาษาไทย");
  for (let i = 0; i < 2; i++) await field.getByRole("button", { name: "ตรวจ", exact: true }).click();
  await expect(field.getByTestId("field-error").first()).toHaveClass(/text-red-700/);
  const before = await (await request.get(`${backend}/api/test-cases/${result.test_case_id}`)).json();
  expect(before.runs[0].fields[0].ground_truth_raw).toBeNull();
  await field.getByRole("button", { name: "ยืนยัน GT Field", exact: true }).click();
  await expect(page.getByTestId("field-summary")).toContainText("ยืนยัน 1/1 Fields");
  await expect(page.getByTestId("field-summary")).toContainText("CER");
  await expect(page.getByTestId("field-summary")).toContainText("WER");
  await page.goto(`/test/${result.test_case_id}`);
  await page.getByRole("tab", { name: "Thai FT v2", exact: true }).click();
  await expect(page.getByTestId("field-summary")).toContainText("ยืนยัน 1/1 Fields");
  // Whole-document GT remains separate and supplies existing analytics.
  await page.getByRole("button", { name: "ทั้งเอกสาร / ROI", exact: true }).click();
  await page.getByLabel(t("What should the document say?"), { exact: true }).fill("ภาษาไทย");
  await page.getByRole("button", { name: t("Confirm ground truth"), exact: true }).click();
  await expect(page.getByText(t("CONFIRMED"), { exact: true })).toBeVisible();
  await page.goto(`/history?pipeline=thai_ft_v2`);
  await expect(page.locator(`a[href="/test/${result.test_case_id}"]`).first()).toBeVisible();
  await page.goto("/matrix?pipeline=thai_ft_v2");
  await expect(page.locator("tbody tr").filter({ hasText: "Thai FT v2" }).first()).toBeVisible();
  await page.goto(`/analytics/errors?test_case_id=${result.test_case_id}`);
  await page.getByLabel("Pipeline", { exact: true }).selectOption("thai_ft_v2");
  await expect(page.locator("tbody tr").first()).toContainText("Thai FT v2");
  await page.goto("/");
  await page.locator('input[type="file"]').first().setInputFiles(path.resolve("public/sample-document.png"));
  await page.getByRole("button", { name: t("Draw test region"), exact: true }).click();
  const b = (await page.getByTestId("document-viewer").locator(".konvajs-content").boundingBox())!;
  const scale = Math.min((b.width - 64) / 1000, (b.height - 64) / 1320, 1);
  const x = b.x + (b.width - 1000 * scale) / 2, y = b.y + (b.height - 1320 * scale) / 2;
  await page.mouse.move(x + 100 * scale, y + 250 * scale); await page.mouse.down();
  await page.mouse.move(x + 750 * scale, y + 350 * scale, { steps: 10 }); await page.mouse.up();
  await page.getByRole("button", { name: "ยืนยัน ROI", exact: true }).click();
  pending = page.waitForResponse(r => r.url().endsWith("/run") && r.request().method() === "POST");
  await page.getByRole("button", { name: t("Run all pipelines"), exact: true }).click();
  const manual = await (await pending).json();
  expect(manual.runs.map((r: PipelineRun) => r.pipeline_id).sort()).toEqual(configs.map(c => c.pipeline_id).sort());
  expect(manual.runs.every((r: PipelineRun) => r.status === "success")).toBeTruthy();
  expect(new Set(manual.runs.map((r: PipelineRun) => r.input_sha256)).size).toBe(1);
  expect(manual.runs.find((r: PipelineRun) => r.pipeline_id === "hutch_full").crop_stage).toBe("manual_roi");
});
