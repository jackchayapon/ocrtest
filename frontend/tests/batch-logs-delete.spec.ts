import { test, expect } from "@playwright/test";
import path from "node:path";

const backend = process.env.E2E_API_URL || "http://127.0.0.1:8000";

test("selected PDF pages run separately; logs and confirmed deletion preserve document", async ({
  page,
  request,
}) => {
  for (const id of ["mint", "hutch_crop", "hutch_full"])
    await request.put(`${backend}/api/pipelines/${id}`, {
      data: { enabled: true },
    });
  await page.goto("/");
  const uploaded = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/documents") && r.request().method() === "POST",
  );
  await page
    .locator('input[type="file"]')
    .first()
    .setInputFiles(path.resolve("tests/fixtures/two-pages.pdf"));
  const document = await (await uploaded).json();
  await page.getByRole("tab", { name: "หลายหน้า PDF", exact: true }).click();
  const panel = page.getByRole("region", { name: "เลือกหลายหน้า PDF" });
  await expect(panel).toBeVisible();
  await panel.locator("summary").click();
  await panel.getByLabel("ช่วงหน้า PDF").fill("2, 1, 2");
  await expect(panel).toContainText("เลือกแล้ว 2 หน้า");
  await panel.getByLabel("ช่วงหน้า PDF").fill("0");
  await expect(
    page.getByRole("button", { name: "ประมวลผลหน้าที่เลือก", exact: true }),
  ).toBeDisabled();
  await panel.getByRole("button", { name: "เลือกทุกหน้า" }).click();
  await expect(panel.getByLabel("เลือกหน้า 1", { exact: true })).toBeChecked();
  await page
    .getByRole("button", { name: "ประมวลผลหน้าที่เลือก", exact: true })
    .click();
  await expect(
    panel.getByRole("link", { name: "เปิดผลและแก้ Ground Truth" }),
  ).toHaveCount(2);
  await expect(panel.locator("li").nth(0)).toContainText("หน้า 1 · สำเร็จ");
  await expect(panel.locator("li").nth(1)).toContainText("หน้า 2 · สำเร็จ");
  const cases = await panel
    .getByRole("link", { name: "เปิดผลและแก้ Ground Truth" })
    .evaluateAll((links) =>
      links.map(
        (link) => (link as HTMLAnchorElement).pathname.split("/").pop()!,
      ),
    );
  expect(cases).toHaveLength(2);
  for (const id of cases) {
    const saved = await (
      await request.get(`${backend}/api/test-cases/${id}`)
    ).json();
    expect(saved.runs).toHaveLength(5);
    expect(saved.ground_truth_raw).toBeNull();
  }
  await page.goto(`/logs?test_case_id=${cases[0]}`);
  await expect(
    page.getByRole("heading", { name: "บันทึกการทำงาน" }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "ocr_run_success", exact: true }),
  ).toHaveCount(5);
  await page.getByLabel("ระดับ", { exact: true }).selectOption("ERROR");
  await expect(
    page.getByRole("cell", { name: "ocr_run_success", exact: true }),
  ).toHaveCount(0);
  await page.goto(`/history?document=${document.id}`);
  const row = page
    .getByRole("row")
    .filter({ has: page.locator(`a[href="/test/${cases[0]}"]`) });
  await row.getByRole("button", { name: "ลบประวัติ", exact: true }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText("เอกสารต้นฉบับ");
  await expect(dialog.getByRole("button", { name: "ยกเลิก" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(
    dialog.getByRole("button", { name: "ยืนยันลบประวัติ" }),
  ).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "ยกเลิก" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(
    row.getByRole("button", { name: "ลบประวัติ", exact: true }),
  ).toBeFocused();
  await row.getByRole("button", { name: "ลบประวัติ", exact: true }).click();
  await dialog.getByRole("button", { name: "ยกเลิก" }).click();
  expect(
    (await request.get(`${backend}/api/test-cases/${cases[0]}`)).status(),
  ).toBe(200);
  await row.getByRole("button", { name: "ลบประวัติ", exact: true }).click();
  await dialog.getByRole("button", { name: "ยืนยันลบประวัติ" }).click();
  await expect(dialog).toBeHidden();
  expect(
    (await request.get(`${backend}/api/test-cases/${cases[0]}`)).status(),
  ).toBe(404);
  expect(
    (await request.get(`${backend}/api/test-cases/${cases[1]}`)).status(),
  ).toBe(200);
  expect(
    (
      await request.get(`${backend}/api/documents/${document.id}/pages/1/image`)
    ).status(),
  ).toBe(200);
});
