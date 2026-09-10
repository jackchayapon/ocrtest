import { t } from "../lib/i18n/th";
import { expect, test } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";
import type { PipelineRun, TestCase } from "../types";

const backend = process.env.E2E_API_URL || "http://127.0.0.1:8000";

for (const imageFile of ["public/sample-document.png", "tests/fixtures/sample-document.jpg"]) {
test(`upload ${imageFile}, original-coordinate ROI, two upstream results and unresolved Full contract, ground truth, saved detail and dashboards`, async ({ page, request }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  const configs = await (await request.get(`${backend}/api/pipelines`)).json();
  for (const config of configs) {
    expect((await request.put(`${backend}/api/pipelines/${config.pipeline_id}`, { data: { enabled: true } })).ok()).toBeTruthy();
  }
  await page.goto("/");
  await expect(page.getByRole("button", { name: t("Upload document"), exact: true })).toBeEnabled();
  await page.locator('input[type="file"]').first().setInputFiles(path.resolve(imageFile));
  const viewer = page.getByTestId("document-viewer");
  await expect(viewer).toBeVisible();
  await expect(viewer.getByText(t("Loading document…"), { exact: true })).toBeHidden();
  await page.getByRole("button", { name: t("Draw test region"), exact: true }).click();
  const canvas = viewer.locator(".konvajs-content");
  const frame = await canvas.boundingBox();
  expect(frame).not.toBeNull();
  const box = frame!;
  const scale = Math.min((box.width - 64) / 1000, (box.height - 64) / 1320, 1);
  const origin = { x: box.x + (box.width - 1000 * scale) / 2, y: box.y + (box.height - 1320 * scale) / 2 };
  // Reverse-direction drag checks that ROI endpoints are canonicalized.
  await page.mouse.move(origin.x + 850 * scale, origin.y + 355 * scale);
  await page.mouse.down();
  await page.mouse.move(origin.x + 80 * scale, origin.y + 225 * scale, { steps: 12 });
  await page.mouse.up();
  await expect(page.getByAltText(t("Selected test region crop"))).toBeVisible();
  const roiBeforeZoom = await viewer.getByText(/^พื้นที่ที่เลือก \(ROI\) \(/).textContent();
  await page.getByRole("button", { name: t("Zoom in"), exact: true }).click();
  expect(await viewer.getByText(/^พื้นที่ที่เลือก \(ROI\) \(/).textContent()).toEqual(roiBeforeZoom);
  await page.getByRole("button", { name: t("Fit document to view"), exact: true }).click();
  await page.getByLabel(t("What should the document say?")).fill("บริษัท ซีดีจี จำกัด");
  await page.getByRole("button", { name: /^ข้อความภาษาไทย$/ }).click();
  for (const name of [t("Mint Custom"), "Hutch Crop", "Hutch Full"]) {
    await expect(page.getByLabel(`เลือก ${name}`, { exact: true })).toBeChecked();
  }
  const responsePromise = page.waitForResponse(response => /\/api\/test-cases\/[^/]+\/run$/.test(response.url()) && response.request().method() === "POST");
  await page.getByRole("button", { name: t("Run all pipelines"), exact: true }).click();
  const result = await (await responsePromise).json();
  expect(result.runs).toHaveLength(3);
  expect(result.runs.map((run: PipelineRun) => run.status)).toEqual(["success", "success", "error"]);
  expect(result.runs[2].error_code).toBe("ROI_CONTRACT_UNCONFIRMED");
  const hashes = result.runs.slice(0, 2).map((run: { crop_sha256: string }) => run.crop_sha256);
  expect(hashes[0]).toMatch(/^[a-f0-9]{64}$/);
  expect(new Set(hashes).size).toBe(1);
  expect(result.runs.find((run: { pipeline_id: string }) => run.pipeline_id === "hutch_full").crop_stage).toBe("external_hutch");
  await expect(page.getByTestId("result-text-mint")).toHaveText("บริษัท ซีดีจี จำกัด");
  await page.getByTestId("technical-details").locator("summary").first().click();
  await expect(page.getByText(t("SAME INPUT"), { exact: true })).toBeVisible();
  await expect(page.getByAltText(t("Selected test region crop"))).toBeVisible();
  const mintCard = page.locator('article[aria-label="ผลลัพธ์ Mint Pipeline"]');
  await expect(page.locator("main")).not.toContainText(/MOCK|โหมดจำลอง/);
  await mintCard.getByRole("button", { name: /^กรอบที่ 1/ }).click();
  await expect(mintCard.getByRole("button", { name: /^กรอบที่ 1/ })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText(t("Selected text"), { exact: true })).toBeVisible();
  const prediction = await page.getByTestId("result-text-mint").textContent();
  await page.getByLabel(t("What should the document say?")).fill("บริษัท ซีดีจี จำกัด!");
  await page.getByRole("button", { name: t("Confirm ground truth"), exact: true }).click();
  await expect(page.getByText(t("CONFIRMED"), { exact: true })).toBeVisible();
  expect(await page.getByTestId("result-text-mint").textContent()).toBe(prediction);
  await page.screenshot({ path: "test-results/workspace-desktop.png", fullPage: true });
  await page.goto(`/test/${result.test_case_id}`);
  await expect(page.getByRole("heading", { name: t("Test case detail"), exact: true })).toBeVisible();
  await expect(page.getByLabel(t("What should the document say?"))).toHaveValue("บริษัท ซีดีจี จำกัด!");
  await page.getByTestId("technical-details").locator("summary").first().click();
  await expect(page.getByText(t("SAME INPUT"), { exact: true })).toBeVisible();
  const diagnostic = page.getByRole("region", { name: t("Crop and Gateway debug information") });
  for (const label of ["ภาพต้นฉบับ / ภาพอินพุต", t("Encoded input"), t("Detector"), t("Recognizer"), t("Total / Gateway"), t("Gateway request ID")]) {
    await expect(diagnostic.getByText(label, { exact: true })).toHaveCount(3);
  }
  const persisted: TestCase = await (await request.get(`${backend}/api/test-cases/${result.test_case_id}`)).json();
  expect(persisted.status).toBe("confirmed");
  expect(persisted.runs).toHaveLength(3);
  for (const run of persisted.runs) {
    if (run.pipeline_id === "hutch_full") {
      expect(run.error_code).toBe("ROI_CONTRACT_UNCONFIRMED");
      expect(run.crop_sha256).toBeNull();
      expect(run.input_width).toBe(1000);
      expect(run.input_height).toBe(1320);
      expect(run.metrics).toBeNull();
      continue;
    }
    expect(run.raw_text).toBeTruthy();
    expect(run.metrics?.cer).toBeGreaterThanOrEqual(0);
    expect(run.metrics?.wer).toBeGreaterThanOrEqual(0);
    expect(typeof run.metrics?.exact_match).toBe("boolean");
    expect(run.confidence).not.toBeNull();
    expect(run.gateway_request_id).toBe("fixture-request");
    expect(run.gateway_duration_ms).toBe(123.4);
    const card = page.locator("article").filter({ has: page.getByTestId(`result-text-${run.pipeline_id}`) });
    await card.getByText(t("Raw OCR & metrics"), { exact: true }).click();
    await expect(card.getByText(t("CONFIDENCE"), { exact: true })).toBeVisible();
  }
  // Only the browser fixture differs; saved database hashes are never changed.
  const detailEndpoint = `**/api/test-cases/${result.test_case_id}`;
  await page.route(detailEndpoint, route => route.fulfill({ json: {
    ...persisted, runs: persisted.runs.map((run, index) => index ? run : { ...run, crop_sha256: "0".repeat(64) }),
  } }));
  await page.reload();
  await page.getByTestId("technical-details").locator("summary").first().click();
  await expect(page.getByText(t("DIFFERENT INPUT"), { exact: true })).toBeVisible();
  await page.unroute(detailEndpoint);
  await page.goto("/history");
  await page.locator(`a[href="/test/${result.test_case_id}"]`).first().click();
  await page.getByTestId("technical-details").locator("summary").first().click();
  await expect(page.getByText(t("SAME INPUT"), { exact: true })).toBeVisible();
  fs.mkdirSync("test-results", { recursive: true });
  fs.writeFileSync("test-results/final-benchmark.json", JSON.stringify({
    test_case_id: persisted.id, document_id: persisted.document_id,
    runs: persisted.runs.map((run: PipelineRun) => ({ pipeline_id: run.pipeline_id, crop_sha256: run.crop_sha256, crop_width: run.crop_width, crop_height: run.crop_height, crop_stage: run.crop_stage })),
  }, null, 2));
  for (const route of ["/history", "/matrix", "/analytics/categories", "/settings/pipelines"]) {
    await page.goto(route);
    await expect(page.locator("main h1")).toBeVisible();
    await expect(page.locator("main").getByRole("alert")).toHaveCount(0);
    await expect(page.getByText("Cannot reach the backend", { exact: false })).toHaveCount(0);
  }
  await page.goto("/matrix");
  await expect(page.locator("tbody tr")).toHaveCount(3);
  await page.screenshot({ path: "test-results/matrix-desktop.png", fullPage: true });
  expect(errors).toEqual([]);
});

}

test("mobile workspace fits the viewport and upload remains usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("button", { name: t("Upload document"), exact: true })).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: "test-results/workspace-mobile.png", fullPage: true });
});

test("ROI move and resize, selectable Auto ROI, and failure recovery", async ({ page, request }) => {
  const document = await (await request.post(`${backend}/api/documents`, { multipart: { file: { name: "viewer-fixture.png", mimeType: "image/png", buffer: fs.readFileSync(path.resolve("public/sample-document.png")) } } })).json();
  const saved = await (await request.post(`${backend}/api/test-cases`, { data: { document_id: document.id, roi: { x1: 100, y1: 200, x2: 700, y2: 400 } } })).json();
  await page.goto(`/test/${saved.id}`);
  const viewer = page.getByTestId("document-viewer");
  await expect(viewer.getByText(t("Loading document…"), { exact: true })).toBeHidden();
  await expect(viewer.getByText(/^พื้นที่ที่เลือก \(ROI\) \(/)).toBeVisible();
  const point = async (x: number, y: number) => {
    await viewer.locator(".konvajs-content").scrollIntoViewIfNeeded();
    const frame = (await viewer.locator(".konvajs-content").boundingBox())!;
    const scale = Math.min((frame.width - 64) / 1000, (frame.height - 64) / 1320, 1);
    return { x: frame.x + (frame.width - 1000 * scale) / 2 + x * scale, y: frame.y + (frame.height - 1320 * scale) / 2 + y * scale };
  };
  const readROI = async () => (await viewer.getByText(/^พื้นที่ที่เลือก \(ROI\) \(/).textContent())!.match(/\d+/g)!.slice(0, 4).map(Number);
  const center = await point(400, 300);
  await page.mouse.move(center.x, center.y);
  await page.mouse.down();
  await page.mouse.move(center.x + 25, center.y + 15, { steps: 8 });
  await page.mouse.up();
  const moved = await readROI();
  expect(moved[0]).toBeGreaterThan(100);
  expect(moved[1]).toBeGreaterThan(200);
  expect(moved[2] - moved[0]).toBe(600);
  expect(moved[3] - moved[1]).toBe(200);
  const corner = await point(moved[2], moved[3]);
  await page.mouse.move(corner.x, corner.y);
  await page.mouse.down();
  await page.mouse.move(corner.x + 20, corner.y + 15, { steps: 8 });
  await page.mouse.up();
  const resized = await readROI();
  expect(resized[2] - resized[0]).toBeGreaterThan(600);
  expect(resized[3] - resized[1]).toBeGreaterThan(200);
  expect(resized[2]).toBeLessThanOrEqual(1000);
  expect(resized[3]).toBeLessThanOrEqual(1320);
  // The test-only upstream rejects layout mode; exercise the actual backend error path.
  await page.getByLabel(t("Auto ROI mode")).selectOption("layout");
  await page.getByRole("button", { name: t("Auto Detect"), exact: true }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText("ไม่สามารถตรวจหาพื้นที่อัตโนมัติได้ในขณะนี้");
  await expect(page.getByRole("button", { name: t("Run all pipelines"), exact: true })).toBeEnabled();
  expect(await readROI()).toEqual(resized);
  await page.getByLabel(t("Auto ROI mode")).selectOption("text-line");
  await page.getByRole("button", { name: t("Auto Detect"), exact: true }).click();
  await expect(page.getByRole("button", { name: /^พื้นที่ 1/ })).toBeVisible();
  const suggestion = await point(400, 280);
  await page.mouse.click(suggestion.x, suggestion.y);
  expect(await readROI()).toEqual([80, 225, 850, 355]);
  await expect(page.getByRole("button", { name: /^พื้นที่ 1/ })).toHaveCount(0);
  await page.getByLabel("เลือก Hutch Crop").uncheck();
  await page.getByLabel("เลือก Hutch Full").uncheck();
  const pending = page.waitForResponse(response => response.url().endsWith("/run") && response.request().method() === "POST");
  await page.getByRole("button", { name: t("Run selected"), exact: true }).click();
  const result = await (await pending).json();
  expect(result.runs).toHaveLength(1);
  await expect(page.getByTestId("result-text-mint")).toBeVisible();
  const bbox = result.runs[0].boxes[0].bbox;
  const textPoint = await point((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2);
  await page.mouse.click(textPoint.x, textPoint.y);
  await expect(page.locator('article[aria-label="ผลลัพธ์ Mint Pipeline"]').getByRole("button", { name: /^กรอบที่ 1/ })).toHaveAttribute("aria-pressed", "true");
});

test("settings save and upstream connection test", async ({ page }) => {
  await page.goto("/settings/pipelines");
  const card = page.locator("section").filter({ has: page.getByRole("heading", { name: t("Mint Custom"), exact: true }) });
  await expect(card.getByText(/ตั้งค่า API Key แล้ว:/)).toBeVisible();
  const enabled = card.getByLabel(t("Pipeline enabled"));
  await enabled.uncheck();
  await expect(card.getByRole("button", { name: t("Test connection"), exact: true })).toBeDisabled();
  await card.getByRole("button", { name: t("Save changes"), exact: true }).click();
  await expect(card.getByText(t("Pipeline settings saved."))).toBeVisible();
  await enabled.check();
  await card.getByRole("button", { name: t("Save changes"), exact: true }).click();
  await expect(card.getByRole("button", { name: t("Saved"), exact: true })).toBeVisible();
  await card.getByRole("button", { name: t("Test connection"), exact: true }).click();
  await expect(card.getByText("พร้อมใช้งาน", { exact: true }).first()).toBeVisible();
});
