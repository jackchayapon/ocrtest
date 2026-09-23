import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { t } from "../lib/i18n/th";

const backend = process.env.E2E_API_URL || "http://127.0.0.1:8000";

test("confirmed source crop dataset export and persisted error analysis drilldown", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const doc = await (
    await request.post(`${backend}/api/documents`, {
      multipart: {
        file: {
          name: "dataset-source.png",
          mimeType: "image/png",
          buffer: fs.readFileSync(path.resolve("public/sample-document.png")),
        },
      },
    })
  ).json();
  const saved = await (
    await request.post(`${backend}/api/test-cases`, {
      data: {
        document_id: doc.id,
        roi: { x1: 80, y1: 225, x2: 850, y2: 355 },
        category_codes: ["thai_text"],
      },
    })
  ).json();
  await request.post(`${backend}/api/test-cases/${saved.id}/run`, {
    data: { pipelines: ["mint", "hutch_crop", "hutch_full"] },
  });
  await page.goto(`/test/${saved.id}`);
  await page.getByRole("button", { name: "ทั้งเอกสาร / ROI", exact: true }).click();
  await page
    .getByLabel(t("What should the document say?"), { exact: true })
    .fill("Confirmed Thai ก\nLabel");
  await page
    .getByRole("button", { name: t("Confirm ground truth"), exact: true })
    .click();
  await expect(page.getByText(t("CONFIRMED"), { exact: true })).toBeVisible();
  await page
    .getByRole("link", { name: "วิเคราะห์ข้อผิดพลาดของชุดทดสอบนี้" })
    .click();
  await expect(
    page.getByRole("heading", { name: "วิเคราะห์ข้อผิดพลาด OCR" }),
  ).toBeVisible();
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await page.getByLabel("Pipeline", { exact: true }).selectOption("mint");
  await page.getByLabel("ระดับ", { exact: true }).selectOption("word");
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await page.locator("tbody details summary").first().click();
  await expect(
    page.locator(`tbody a[href="/test/${saved.id}"]`).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "คำนวณรายละเอียดใหม่" }).click();
  await expect(page.locator(".notice-banner")).toContainText("คำนวณข้อผิดพลาด");
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await page.setViewportSize({ width: 768, height: 1024 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(768);
  await page.screenshot({ path: "test-results/error-analysis-768.png", fullPage: true });
  await page.goto("/dataset");
  await page.getByLabel("Document ID").fill(doc.id);
  const row = page
    .locator("tbody tr")
    .filter({ hasText: "dataset-source.png" });
  await expect(row).toContainText("Confirmed Thai ก");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(768);
  await page.screenshot({ path: "test-results/dataset-768.png", fullPage: true });
  await expect
    .poll(() =>
      row
        .locator("img")
        .evaluate((img) => (img as HTMLImageElement).naturalWidth),
    )
    .toBe(770);
  await row.getByRole("checkbox").check();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "ส่งออก ZIP (1)" }).click();
  const file = await downloaded;
  expect(file.suggestedFilename()).toBe("dataset.zip");
  expect(await file.failure()).toBeNull();
  await row.getByRole("link").click();
  await page.getByRole("button", { name: "ทั้งเอกสาร / ROI", exact: true }).click();
  await expect(
    page.getByLabel(t("What should the document say?"), { exact: true }),
  ).toHaveValue("Confirmed Thai ก\nLabel");
  expect(errors).toEqual([]);
});

test("new views have honest empty, failure and responsive states", async ({
  page,
}) => {
  for (const [route, endpoint, empty] of [
    ["/dataset", "**/api/dataset/samples?*", "ยังไม่มีตัวอย่างที่พร้อมส่งออก"],
    [
      "/analytics/errors",
      "**/api/analytics/errors?*",
      "ยังไม่มีรายละเอียดข้อผิดพลาด",
    ],
  ]) {
    await page.route(endpoint, (r) =>
      r.fulfill({ json: { total: 0, items: [] } }),
    );
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto(route);
    await expect(page.getByRole("heading", { name: empty })).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(768);
    await page.unroute(endpoint);
    await page.route(endpoint, (r) =>
      r.fulfill({ status: 503, json: { detail: "Test unavailable" } }),
    );
    await page.reload();
    await expect(page.locator("main").getByRole("alert")).toBeVisible();
    await expect(page.getByRole("heading", { name: empty })).toHaveCount(0);
    await page.unroute(endpoint);
  }
});
