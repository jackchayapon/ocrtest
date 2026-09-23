import { test, expect } from "@playwright/test";
import path from "node:path";

const api = process.env.E2E_API_URL || "http://127.0.0.1:8100";

test("batch selection is independent of preview; selected page results and GT stay inline", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await page
    .locator('input[type="file"]')
    .first()
    .setInputFiles(path.resolve("tests/fixtures/two-pages.pdf"));
  await page.getByRole("tab", { name: "หลายหน้า PDF", exact: true }).click();
  const rail = page.getByRole("region", { name: "เลือกหลายหน้า PDF" });
  await expect(page.locator("#ground-truth")).toHaveCount(0);
  await rail.getByLabel("เลือกหน้า 2", { exact: true }).check();
  await expect(page.getByTestId("pdf-page-indicator")).toContainText(
    "หน้า 1 จาก 2",
  );
  await rail.getByRole("button", { name: "พรีวิวหน้า 2", exact: true }).click();
  await expect(
    rail.getByRole("button", { name: "พรีวิวหน้า 2", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await expect(
    rail.getByLabel("เลือกหน้า 1", { exact: true }),
  ).not.toBeChecked();
  await expect(rail.getByLabel("เลือกหน้า 2", { exact: true })).toBeChecked();
  await rail.getByRole("button", { name: "เลือกทุกหน้า" }).click();
  await expect(rail).toContainText("เลือกแล้ว 2 หน้า");
  await rail.getByRole("button", { name: "ล้างหน้า" }).click();
  await expect(rail).toContainText("เลือกแล้ว 0 หน้า");
  await rail.getByLabel("เลือกหน้า 2", { exact: true }).check();
  const pending = page.waitForResponse(
    (r) => r.url().endsWith("/run-pages") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "ประมวลผลหน้าที่เลือก", exact: true })
    .click();
  const response = await pending;
  expect(response.request().postDataJSON().pages).toEqual([2]);
  await expect(
    rail.getByRole("button", { name: "ดูผลหน้า 2", exact: true }),
  ).toBeEnabled();
  await expect(rail.locator(".batch-progress li")).toHaveCount(1);
  const savedUrl = await rail
    .getByRole("link", { name: "เปิดผลและแก้ Ground Truth" })
    .getAttribute("href");
  const savedId = savedUrl!.split("/").pop();
  await rail.getByRole("button", { name: "ดูผลหน้า 2", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId("result-text-mint")).toBeVisible();
  await page.getByRole("button", { name: "ทั้งเอกสาร / ROI", exact: true }).click();
  await expect(page.locator("#ground-truth")).toHaveValue("");
  await page.getByRole("button", { name: "ทั้งเอกสาร / ROI", exact: true }).click();
  await page.locator("#ground-truth").fill("ข้อความอ้างอิงเฉพาะหน้า 2");
  await page
    .getByRole("button", { name: "บันทึกข้อความที่ถูกต้อง", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "บันทึกข้อความที่ถูกต้อง", exact: true }),
  ).toBeEnabled();
  await expect(page).toHaveURL(/\/$/);
  const saved = await (
    await request.get(`${api}/api/test-cases/${savedId}`)
  ).json();
  expect(saved.page_number).toBe(2);
  expect(saved.ground_truth_raw).toBe("ข้อความอ้างอิงเฉพาะหน้า 2");
  await rail.getByRole("button", { name: "พรีวิวหน้า 1", exact: true }).click();
  await expect(page.locator("#ground-truth")).toHaveCount(0);
  await rail.getByRole("button", { name: "ดูผลหน้า 2", exact: true }).click();
  await page.getByRole("button", { name: "ทั้งเอกสาร / ROI", exact: true }).click();
  await expect(page.locator("#ground-truth")).toHaveValue(
    "ข้อความอ้างอิงเฉพาะหน้า 2",
  );
  await page.screenshot({
    path: "test-results/batch-inline-review.png",
    fullPage: true,
  });
});

test("batch retries only failed pages and preserves completed progress", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .locator('input[type="file"]')
    .first()
    .setInputFiles(path.resolve("tests/fixtures/two-pages.pdf"));
  await page.getByRole("tab", { name: "หลายหน้า PDF", exact: true }).click();
  const rail = page.getByRole("region", { name: "เลือกหลายหน้า PDF" });
  const submitted: number[][] = [];
  await page.route("**/api/documents/*/run-pages", (route) => {
    submitted.push(route.request().postDataJSON().pages);
    const rows =
      submitted.length === 1
        ? [
            { event: "page_started", page: 1, status: "running" },
            { event: "page_finished", page: 1, status: "success" },
            { event: "page_started", page: 2, status: "running" },
            { event: "page_finished", page: 2, status: "error" },
          ]
        : [
            { event: "page_started", page: 2, status: "running" },
            { event: "page_finished", page: 2, status: "success" },
          ];
    return route.fulfill({
      contentType: "application/x-ndjson",
      body:
        [...rows, { event: "batch_finished" }]
          .map((e) => JSON.stringify(e))
          .join("\n") + "\n",
    });
  });
  await rail.getByRole("button", { name: "เลือกทุกหน้า" }).click();
  await page
    .getByRole("button", { name: "ประมวลผลหน้าที่เลือก", exact: true })
    .click();
  await expect(rail.locator(".batch-progress li").nth(0)).toContainText(
    "หน้า 1 · สำเร็จ",
  );
  await expect(rail.locator(".batch-progress li").nth(1)).toContainText(
    "หน้า 2 · ผิดพลาด",
  );
  await rail
    .getByRole("button", { name: "ลองหน้าที่ผิดพลาดใหม่ (สร้างชุดทดสอบใหม่)" })
    .click();
  await expect(rail.locator(".batch-progress li").nth(1)).toContainText(
    "หน้า 2 · สำเร็จ",
  );
  await expect(rail.locator(".batch-progress li").nth(0)).toContainText(
    "หน้า 1 · สำเร็จ",
  );
  expect(submitted).toEqual([[1, 2], [2]]);
});
