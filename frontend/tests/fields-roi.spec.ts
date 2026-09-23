import { expect, test } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";
import { t } from "../lib/i18n/th";
const api = process.env.E2E_API_URL || "http://127.0.0.1:8000";

test("PDF pages retain separate Auto ROI suggestions without another detection request", async ({ page }) => {
  let detections = 0;
  page.on("request", r => { if (r.url().includes("/auto-rois")) detections++; });
  await page.goto("/");
  await page.locator('input[type="file"]').first().setInputFiles(path.resolve("tests/fixtures/two-pages.pdf"));
  await page.getByRole("button", { name: t("Auto Detect"), exact: true }).click();
  await expect(page.getByRole("button", { name: "พื้นที่ 2", exact: true })).toBeVisible();
  await page.getByRole("button", { name: t("Next page"), exact: true }).click();
  await expect(page.getByTestId("pdf-page-indicator")).toHaveText("หน้า 2 จาก 2");
  await expect(page.getByRole("button", { name: "พื้นที่ 2", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: t("Auto Detect"), exact: true }).click();
  await expect(page.getByRole("button", { name: "พื้นที่ 2", exact: true })).toBeVisible();
  await page.getByRole("button", { name: t("Previous page"), exact: true }).click();
  await expect(page.getByTestId("pdf-page-indicator")).toHaveText("หน้า 1 จาก 2");
  await expect(page.getByRole("button", { name: "พื้นที่ 1", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "พื้นที่ 2", exact: true })).toBeVisible();
  expect(detections).toBe(2);
});

test("default field GT uses Check preview, accessible red errors and explicit confirmation", async ({ page, request }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').first().setInputFiles(path.resolve("public/sample-document.png"));
  await expect(page.getByRole("button", { name: "ราย Field", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#ground-truth")).toHaveCount(0);
  const pending = page.waitForResponse(r => r.url().endsWith("/run") && r.request().method() === "POST");
  await page.getByRole("button", { name: t("Run all pipelines"), exact: true }).click();
  const result = await (await pending).json();
  await page.getByRole("tab", { name: t("Mint Custom"), exact: true }).click();
  await expect(page.getByTestId("ocr-field")).toHaveCount(2);
  const field = page.getByTestId("ocr-field").nth(1);
  await expect(field).toContainText("OCR: ABCD");
  await expect(field).toContainText("Confidence 93.00%");
  await field.getByRole("button", { name: "Field 02", exact: true }).click();
  await expect(field.getByRole("button", { name: "Field 02" })).toHaveAttribute("aria-pressed", "true");
  for (const [gt, kind] of [["ABXD", "substitution"], ["ABD", "insertion"], ["ABXCD", "deletion"], ["ABCD", "equal"]]) {
    await field.getByLabel("GT Field 2", { exact: true }).fill(gt);
    await expect(field.getByRole("button", { name: "ยืนยัน GT Field", exact: true })).toBeDisabled();
    await field.getByRole("button", { name: "ตรวจ", exact: true }).click();
    if (kind === "equal") await expect(field.getByTestId("field-error")).toHaveCount(0);
    else {
      const mark = field.locator(`[data-error-type="${kind}"]`).first();
      await expect(mark).toBeVisible(); await expect(mark).toHaveClass(/text-red-700/);
      await expect(mark).toHaveAttribute("aria-label", /อ่าน/);
      if (kind === "deletion") await expect(mark).toHaveText("⟦ขาด: X⟧");
    }
  }
  const before = await (await request.get(`${api}/api/test-cases/${result.test_case_id}`)).json();
  expect(before.runs[0].fields[1].ground_truth_raw).toBeNull();
  await field.getByRole("button", { name: "ยืนยัน GT Field", exact: true }).click();
  await expect(field).toContainText("ยืนยันแล้ว");
  await expect(page.getByTestId("field-summary")).toContainText("ยืนยัน 1/2 Fields");
  await page.reload();
  await page.getByRole("tab", { name: t("Mint Custom"), exact: true }).click();
  await expect(page.getByTestId("field-summary")).toContainText("ยืนยัน 1/2 Fields");
  await page.getByRole("button", { name: "ทั้งเอกสาร / ROI", exact: true }).click();
  await expect(page.locator("#ground-truth")).toBeVisible();
});

test("Auto suggestions survive selection, editing and manual drawing; Hutch input follows explicit source", async ({ page, request }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').first().setInputFiles(path.resolve("public/sample-document.png"));
  await page.getByRole("button", { name: t("Auto Detect"), exact: true }).click();
  const first = page.getByRole("button", { name: "พื้นที่ 1", exact: true });
  const second = page.getByRole("button", { name: "พื้นที่ 2", exact: true });
  await expect(first).toBeVisible(); await expect(second).toBeVisible();
  await first.click(); await expect(second).toBeVisible();
  await second.click(); await expect(first).toBeVisible();
  await expect(second).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "ยืนยัน ROI", exact: true }).click();
  let pending = page.waitForResponse(r => r.url().endsWith("/run") && r.request().method() === "POST");
  await page.getByRole("button", { name: t("Run all pipelines"), exact: true }).click();
  const auto = await (await pending).json();
  expect(auto.runs[2].input_width).toBe(1000); expect(auto.runs[2].roi).toBeNull();
  expect((await (await request.get(`${api}/api/test-cases/${auto.test_case_id}`)).json()).roi_source).toBe("auto");
  await page.getByRole("button", { name: t("Draw test region"), exact: true }).click();
  const b = (await page.getByTestId("document-viewer").locator(".konvajs-content").boundingBox())!;
  const scale = Math.min((b.width-64)/1000,(b.height-64)/1320,1);
  const x=b.x+(b.width-1000*scale)/2,y=b.y+(b.height-1320*scale)/2;
  await page.mouse.move(x+100*scale,y+250*scale); await page.mouse.down();
  await page.mouse.move(x+750*scale,y+350*scale,{steps:10}); await page.mouse.up();
  await expect(first).toBeVisible(); await expect(second).toBeVisible();
  await expect(page.getByTestId("hutch-input-rule")).toContainText("Manual ROI crop");
  await page.getByRole("button", { name: "ยืนยัน ROI", exact: true }).click();
  pending=page.waitForResponse(r=>r.url().endsWith("/run") && r.request().method()==="POST");
  await page.getByRole("button",{name:t("Run all pipelines"),exact:true}).click();
  const manual=await (await pending).json();
  expect(manual.test_case_id).not.toBe(auto.test_case_id);
  expect(new Set(manual.runs.map((r: {input_sha256:string})=>r.input_sha256)).size).toBe(1);
  expect(manual.runs[2].crop_stage).toBe("manual_roi");
  expect((await (await request.get(`${api}/api/test-cases/${manual.test_case_id}`)).json()).roi_source).toBe("manual");
  await first.click(); await expect(second).toBeVisible();
  await page.getByRole("button",{name:"ใช้ Manual ROI ล่าสุด",exact:true}).click();
  await expect(page.getByTestId("hutch-input-rule")).toContainText("Manual ROI crop");
});

test("Dataset stale-file failure stays actionable and does not hide the selection", async ({ page, request }) => {
  const doc=await (await request.post(`${api}/api/documents`,{multipart:{file:{name:"missing-source.png",mimeType:"image/png",buffer:fs.readFileSync(path.resolve("public/sample-document.png"))}}})).json();
  const c=await (await request.post(`${api}/api/test-cases`,{data:{document_id:doc.id,roi:{x1:10,y1:10,x2:100,y2:100},roi_source:"manual"}})).json();
  await request.put(`${api}/api/test-cases/${c.id}/ground-truth`,{data:{ground_truth_raw:"ไทย",confirmed:true}});
  await page.goto("/dataset"); await page.getByLabel("Document ID").fill(doc.id);
  const row=page.locator("tbody tr").filter({hasText:"missing-source.png"});
  await row.getByRole("checkbox").check();
  // Reproduce the exact storage failure observed on production, after listing but before export.
  const source=path.resolve("../backend/.pytest_e2e/uploads",doc.storage_key);
  expect(path.dirname(source)).toBe(path.resolve("../backend/.pytest_e2e/uploads"));
  const original=fs.readFileSync(source); fs.unlinkSync(source);
  try {
    await page.getByRole("button",{name:"ส่งออก ZIP (1)"}).click();
    await expect(page.locator("main").getByRole("alert")).toContainText("ไม่พบไฟล์ต้นฉบับ");
    await expect(row).toBeVisible();
    await page.getByRole("button",{name:"รีเฟรช",exact:true}).click();
    await expect(row.getByRole("checkbox")).toBeDisabled();
    await expect(row).toContainText("ไฟล์ต้นฉบับไม่อยู่ใน storage");
  } finally { fs.writeFileSync(source,original); }
  await page.getByRole("button",{name:"รีเฟรช",exact:true}).click();
  await row.getByRole("checkbox").check();
  const download=page.waitForEvent("download");
  await page.getByRole("button",{name:"ส่งออก ZIP (1)"}).click();
  expect(await (await download).failure()).toBeNull();
});
