import { expect, test } from "@playwright/test";
import path from "node:path";
import { t } from "../lib/i18n/th";

const backend = process.env.E2E_API_URL || "http://127.0.0.1:8000";

test("Benchmark appears dynamically and flows through ROI, saved metrics, errors and comparison", async ({ page, request }) => {
  await request.put(`${backend}/api/pipelines/benchmark`, { data: { enabled: true } });
  await page.goto("/");
  await page.locator('input[type="file"]').first().setInputFiles(path.resolve("public/sample-document.png"));
  await expect(page.getByTestId("document-viewer")).toBeVisible();
  await page.getByRole("button", { name: t("Auto Detect"), exact: true }).click();
  await page.getByRole("button", { name: /^พื้นที่ 1$/ }).click();
  await page.getByRole("button", { name: "ยืนยัน ROI", exact: true }).click();
  for (const label of [t("Mint Custom"), "Hutch Crop", "Hutch Full"]) {
    await page.getByLabel(`เลือก ${label}`, { exact: true }).uncheck();
  }
  await page.getByLabel("เลือก Benchmark", { exact: true }).check();
  await page.getByLabel(t("What should the document say?"), { exact: true }).fill("ภาษาไทย");
  const pending = page.waitForResponse(r => r.url().endsWith("/run") && r.request().method() === "POST");
  await page.getByRole("button", { name: t("Run selected"), exact: true }).click();
  const data = await (await pending).json();
  expect(data.runs).toHaveLength(1);
  expect(data.runs[0]).toMatchObject({ pipeline_id: "benchmark", status: "success", input_width: 770, input_height: 130 });
  expect(data.runs[0].raw_response.recognition_batches).toHaveLength(1);
  await expect(page.getByTestId("result-text-benchmark")).toHaveText("บริษัท ซีดีจี จำกัด");
  await page.getByRole("button", { name: t("Confirm ground truth"), exact: true }).click();
  await expect(page.getByText(t("CONFIRMED"), { exact: true })).toBeVisible();
  await page.goto(`/test/${data.test_case_id}`);
  await page.getByRole("tab", { name: "Benchmark", exact: true }).click();
  await expect(page.getByTestId("result-text-benchmark")).toBeVisible();
  await page.goto(`/analytics/errors?test_case_id=${data.test_case_id}`);
  await page.getByLabel("Pipeline", { exact: true }).selectOption("benchmark");
  await expect(page.locator("tbody tr").first()).toContainText("Benchmark");
  await page.goto("/history?pipeline=benchmark");
  await expect(page.locator(`a[href="/test/${data.test_case_id}"]`).first()).toBeVisible();
  await page.goto("/matrix?pipeline=benchmark");
  await expect(page.locator("tbody tr").filter({ hasText: "Benchmark" }).first()).toBeVisible();
  await page.goto("/settings/pipelines");
  const card = page.locator("section").filter({ has: page.getByRole("heading", { name: "Benchmark", exact: true }) });
  await expect(card).toContainText("Recognition V5");
  await card.locator("summary").click();
  await expect(card.getByLabel(t("Image field"), { exact: true })).toHaveValue("images");
});
