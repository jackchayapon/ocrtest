import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const api = process.env.E2E_API_URL || "http://127.0.0.1:8100";
let caseId: string;
test.beforeAll(async ({ request }) => {
  const doc = await (
    await request.post(`${api}/api/documents`, {
      multipart: {
        file: {
          name: "console-review.pdf",
          mimeType: "application/pdf",
          buffer: fs.readFileSync(path.resolve("tests/fixtures/two-pages.pdf")),
        },
      },
    })
  ).json();
  const saved = await (
    await request.post(`${api}/api/test-cases`, {
      data: {
        document_id: doc.id,
        page_number: 1,
        roi: { x1: 50, y1: 100, x2: 800, y2: 600 },
        ground_truth_raw: "บริษัท ซีดีจี จำกัด",
        category_codes: ["thai_text"],
      },
    })
  ).json();
  caseId = saved.id;
  await request.post(`${api}/api/test-cases/${caseId}/run`, {
    data: { pipelines: ["mint", "hutch_crop", "hutch_full"] },
  });
});
for (const [width, height] of [
  [1440, 900],
  [1280, 800],
  [768, 1024],
])
  test(`all console routes visual and navigation QA ${width}x${height}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height });
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    for (const route of [
      "/",
      "/history",
      "/matrix",
      "/analytics/categories",
      "/logs",
      "/settings/pipelines",
      `/test/${caseId}`,
    ]) {
      await page.goto(route);
      await expect(page.locator("main h1")).toBeVisible();
      await expect(page.locator("main .loading-state")).toHaveCount(0);
      await expect(page.locator("main").getByRole("alert")).toHaveCount(0);
      if (route.startsWith("/test/")) {
        await expect(page.getByTestId("result-text-mint")).toBeVisible();
        await expect(
          page.getByTestId("document-viewer").locator("canvas").first(),
        ).toBeVisible();
        await page.getByRole("button", { name: "ทั้งเอกสาร / ROI", exact: true }).click();
        await expect(page.locator("#ground-truth")).toHaveValue(
          "บริษัท ซีดีจี จำกัด",
        );
        await expect(page.getByTestId("technical-details")).not.toHaveAttribute(
          "open",
          "",
        );
      }
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(width);
      await page.screenshot({
        path: `test-results/console-${width}-${route.replaceAll("/", "-").replace(caseId, "detail") || "home"}.png`,
        fullPage: true,
      });
      const nav = page.locator('#console-navigation a[aria-current="page"]');
      await expect(nav).toHaveCount(1);
    }
    await page.locator('#console-navigation a[href="/history"]').click();
    await expect(page).toHaveURL(/\/history$/);
    expect(errors).toEqual([]);
  });
test("library filters, detail tabs, missing metrics and category history links", async ({
  page,
  request,
}) => {
  await page.goto("/history?category=thai_text");
  await expect(page.getByLabel("ประเภทข้อมูล", { exact: true })).toHaveValue(
    "thai_text",
  );
  await page.getByLabel("ค้นหาในรายการหน้านี้").fill("console-review.pdf");
  await page.locator(`a[href="/test/${caseId}"]`).first().click();
  await expect(page.getByTestId("result-text-mint")).toBeVisible();
  await page.getByRole("tab", { name: "Hutch Full", exact: true }).click();
  await expect(page.getByTestId("result-text-hutch_full")).toBeVisible();
  await expect(page.getByTestId("result-text-mint")).toHaveCount(0);
  await page
    .getByTestId("technical-details")
    .locator("summary")
    .first()
    .click();
  await expect(page.getByText("SAME INPUT", { exact: true })).toBeVisible();
  await page.goto("/analytics/categories");
  await expect(
    page.getByRole("columnheader", { name: "ตัวอย่าง / มี GT" }),
  ).toBeVisible();
  await page.locator('main a[href="/history?category=thai_text"]').click();
  await expect(page.getByLabel("ประเภทข้อมูล", { exact: true })).toHaveValue(
    "thai_text",
  );
  const original = await (
    await request.get(`${api}/api/test-cases/${caseId}`)
  ).json();
  const created = await request.post(`${api}/api/test-cases`, {
    data: {
      document_id: original.document.id,
      page_number: 1,
      roi: original.roi,
      ground_truth_raw: null,
      category_codes: ["thai_text"],
    },
  });
  expect(created.ok()).toBeTruthy();
  const noGT = await created.json();
  expect(
    (
      await request.post(`${api}/api/test-cases/${noGT.id}/run`, {
        data: { pipelines: ["mint", "hutch_crop", "hutch_full"] },
      })
    ).ok(),
  ).toBeTruthy();
  await page.goto("/matrix");
  const row = page
    .getByRole("table", { name: "เปรียบเทียบรายชุดทดสอบ" })
    .getByRole("row")
    .filter({ has: page.locator(`a[href="/test/${noGT.id}"]`) });
  await expect(row).toContainText("รอ Ground Truth");
  await expect(row).toContainText("CER —");
});
test("all data routes have recoverable errors and intentional empty states", async ({
  page,
}) => {
  for (const [route, endpoint, title, empty] of [
    ["/history", "history", "ยังไม่มีประวัติการทดสอบ", []],
    ["/matrix", "history", "ยังไม่มีผลสำหรับเปรียบเทียบ", []],
    [
      "/analytics/categories",
      "analytics/categories",
      "ยังไม่มีข้อมูลเพียงพอสำหรับวิเคราะห์",
      [],
    ],
    ["/logs", "logs", "ยังไม่มีบันทึกการทำงาน", { total: 0, items: [] }],
  ] as const) {
    const pattern = `**/api/${endpoint}*`;
    await page.route(pattern, (r) => r.fulfill({ json: empty }));
    await page.goto(route);
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
    await page.unroute(pattern);
    await page.route(pattern, (r) =>
      r.fulfill({ status: 503, json: { detail: "Service unavailable" } }),
    );
    await page.reload();
    await expect(page.locator("main").getByRole("alert")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "ลองใหม่", exact: true }),
    ).toBeVisible();
    await page.unroute(pattern);
  }
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "อัปโหลดเอกสาร", exact: true }),
  ).toBeVisible();
  await expect(page.locator("#ground-truth")).toHaveCount(0);
});
test("logs levels, pagination and filters", async ({ page }) => {
  await page.route("**/api/logs*", (r) => {
    const q = new URL(r.request().url()).searchParams;
    const level = q.get("level");
    const items = ["INFO", "WARNING", "ERROR"]
      .filter((v) => !level || v === level)
      .map((v, i) => ({
        id: `${q.get("offset")}-${i}`,
        created_at: "2026-09-14T08:00:00Z",
        level: v,
        event_type: "ocr_run_" + (v === "ERROR" ? "error" : "success"),
        message: "สถานะการทดสอบ",
        page_number: 1,
        pipeline_id: "mint",
        request_id: "safe-request",
        gateway_request_id: "safe-gateway",
        metadata: {},
      }));
    return r.fulfill({ json: { total: level ? 1 : 30, items } });
  });
  await page.goto("/logs");
  for (const level of ["INFO", "WARNING", "ERROR"])
    await expect(
      page.getByRole("cell", { name: level, exact: true }),
    ).toBeVisible();
  await page.getByRole("button", { name: "ถัดไป", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "ก่อนหน้า", exact: true }),
  ).toBeEnabled();
  await page.getByLabel("ระดับ", { exact: true }).selectOption("ERROR");
  await expect(
    page.getByRole("cell", { name: "INFO", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "ล้างตัวกรอง", exact: true }).click();
  await expect(page.getByLabel("ระดับ", { exact: true })).toHaveValue("");
});

test("local loading keeps navigation available and mobile sidebar reaches every route", async ({
  page,
}) => {
  for (const [route, endpoint] of [
    ["/history", "history"],
    ["/matrix", "matrix"],
    ["/analytics/categories", "analytics/categories"],
    ["/logs", "logs"],
    ["/settings/pipelines", "pipelines"],
    [`/test/${caseId}`, `test-cases/${caseId}`],
  ]) {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const pattern = `**/api/${endpoint}*`;
    await page.route(pattern, async (r) => {
      await gate;
      await r.continue();
    });
    await page.goto(route);
    await expect(
      page.locator("main").getByRole("status").first(),
    ).toBeVisible();
    await expect(
      page.getByRole("navigation", { name: "เมนูหลัก" }),
    ).toBeVisible();
    release();
    await page.unrouteAll({ behavior: "wait" });
    await expect(page.locator("main .loading-state")).toHaveCount(0);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  for (const route of [
    "/",
    "/history",
    "/matrix",
    "/analytics/categories",
    "/logs",
    "/settings/pipelines",
  ]) {
    await page.locator('[aria-controls="console-navigation"]').click();
    await page.locator(`#console-navigation a[href="${route}"]`).click();
    await expect(page.locator("main h1")).toBeVisible();
    await expect(
      page.locator('[aria-controls="console-navigation"]'),
    ).toHaveAttribute("aria-expanded", "false");
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(390);
  }
});
