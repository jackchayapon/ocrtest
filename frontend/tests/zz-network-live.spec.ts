import { test, expect } from "@playwright/test";
import path from "node:path";
import { spawnSync } from "node:child_process";
import type { PipelineRun, TestCase } from "../types";

const api = process.env.E2E_API_URL || "http://127.0.0.1:8100";
const definitions = [
  { name: "Network smoke Official", source: "official", execution_mode: "integrated", version: "6", det_weight: "baseline", rec_weight: "baseline" },
  { name: "Network smoke Custom", source: "custom", execution_mode: "integrated", version: "6", det_weight: "baseline", rec_weight: "thai_ft_v1" },
];

test("isolated real backend: browser upload, Auto/Manual layout, multi OCR, GT, History and bundled Matrix", async ({ page, request }) => {
  test.setTimeout(90_000);
  const ids: string[] = [];
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  try {
    for (const definition of definitions) {
      const response = await request.post(`${api}/api/pipelines`, { data: definition });
      expect(response.status()).toBe(201);
      ids.push((await response.json()).pipeline_id);
    }
    const preflight = await request.fetch(`${api}/api/documents`, { method: "OPTIONS", headers: {
      Origin: new URL(process.env.E2E_BASE_URL || "http://127.0.0.1:3100").origin,
      "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type",
    } });
    expect(preflight.status()).toBe(200);
    expect(preflight.headers()["access-control-allow-origin"]).toBe(new URL(process.env.E2E_BASE_URL || "http://127.0.0.1:3100").origin);
    await page.goto("/");
    const uploaded = page.waitForResponse(r => r.url().endsWith("/api/documents") && r.request().method() === "POST");
    await page.locator("input[type=file]").setInputFiles(path.resolve("public/sample-document.png"));
    const document = await (await uploaded).json();
    await expect(page.getByAltText("เอกสารที่อัปโหลด")).toBeVisible();
    await page.getByRole("button", { name: "ถัดไป: จัดการ Layout", exact: true }).click();
    await page.getByRole("button", { name: "Auto Layout", exact: true }).click();
    await expect(page.getByTestId("global-field-nav")).toHaveCount(3);
    await page.getByRole("button", { name: "เพิ่มกรอบ Manual", exact: true }).click();
    const canvas = page.getByTestId("document-viewer").locator(".konvajs-content");
    await canvas.scrollIntoViewIfNeeded();
    const frame = (await canvas.boundingBox())!;
    const scale = Math.min((frame.width - 64) / 1000, (frame.height - 64) / 1320, 1);
    const x = frame.x + (frame.width - 1000 * scale) / 2, y = frame.y + (frame.height - 1320 * scale) / 2;
    await page.mouse.move(x + 100 * scale, y + 800 * scale);
    await page.mouse.down();
    await page.mouse.move(x + 700 * scale, y + 1000 * scale, { steps: 10 });
    await page.mouse.up();
    await expect(page.getByTestId("global-field-nav")).toHaveCount(4);
    const confirmed = page.waitForResponse(r => r.url().endsWith("/global-fields") && r.request().method() === "PUT");
    await page.getByRole("button", { name: "ยืนยัน ROI", exact: true }).click();
    const testCase = await (await confirmed).json() as TestCase;
    expect(testCase.global_fields).toHaveLength(4);
    const manual = testCase.global_fields![3].roi;
    expect(Math.abs(manual.x1 - 100)).toBeLessThanOrEqual(3);
    expect(Math.abs(manual.x2 - 700)).toBeLessThanOrEqual(3);
    // Other suite cases may create legitimate configurations. Select our exact
    // two pipelines instead of assuming an empty registry or a fixed count.
    const options = page.getByTestId("pipeline-options");
    const registry = await (await request.get(`${api}/api/pipelines?fresh=true`)).json();
    await expect(options.getByRole("checkbox")).toHaveCount(registry.length);
    for (const checkbox of await options.getByRole("checkbox").all()) {
      if (await checkbox.isEnabled()) await checkbox.uncheck();
    }
    for (const definition of definitions) {
      await options.getByRole("checkbox", { name: `เลือก ${definition.name}`, exact: true }).check();
    }
    const resultPromise = page.waitForResponse(r => r.url().endsWith("/run") && r.request().method() === "POST");
    await page.getByRole("button", { name: "Run OCR", exact: true }).click();
    const result = await (await resultPromise).json();
    expect(result.runs.map((r: PipelineRun) => r.pipeline_id).sort()).toEqual([...ids].sort());
    expect(result.runs.every((r: PipelineRun) => r.status === "success")).toBe(true);
    await expect(page).toHaveURL(/\/ground-truth$/);
    for (const n of [1, 2, 3, 4]) {
      await page.getByLabel(`Ground Truth Field 0${n}`, { exact: true }).fill("บริษัท ซีดีจี จำกัด ABXD");
    }
    const evaluation = page.waitForResponse(r => r.url().endsWith("/evaluate"));
    await page.getByRole("button", { name: "ยืนยันเพื่อคำนวณ", exact: true }).click();
    expect((await evaluation).status()).toBe(200);
    const saved = await (await request.get(`${api}/api/test-cases/${testCase.id}`)).json();
    expect(saved.runs.every((r: PipelineRun) => r.fields?.some(f => f.evaluation?.cer != null))).toBe(true);
    await page.goto(`/history?document=${document.id}`);
    await expect(page.locator(`a[href="/test/${testCase.id}"]`).first()).toBeVisible();
    await page.locator(`a[href="/test/${testCase.id}"]`).first().click();
    await expect(page).toHaveURL(/\/ground-truth$/);
    let individualReads = 0;
    page.on("request", r => { if (/\/api\/(matrix|analytics\/comparison)(\?|$)/.test(r.url())) individualReads++; });
    const bundle = page.waitForResponse(r => r.url().includes("/api/analytics/summary") && r.url().includes("dashboard=true"));
    await page.goto("/matrix");
    const snapshot = await (await bundle).json();
    expect(snapshot.matrix.map((r: { pipeline_id: string }) => r.pipeline_id)).toEqual(expect.arrayContaining(ids));
    expect(snapshot.comparison).toBeTruthy();
    await expect(page.getByRole("table", { name: "All Pipelines" })).toBeVisible();
    expect(individualReads).toBe(0);
    expect(errors).toEqual([]);
  } finally {
    for (const id of ids) expect((await request.delete(`${api}/api/pipelines/${id}`)).status()).toBe(204);
  }
});

test("isolated real backend: PDF pages, single pipeline, batch, confirmed GT dataset and cache refresh", async ({ page, request }) => {
  test.setTimeout(90_000);
  const created = await request.post(`${api}/api/pipelines`, { data: definitions[0] });
  expect(created.status()).toBe(201);
  const pipeline = await created.json();
  try {
    await page.goto("/");
    const uploaded = page.waitForResponse(r => r.url().endsWith("/api/documents") && r.request().method() === "POST");
    await page.locator("input[type=file]").setInputFiles(path.resolve("tests/fixtures/two-pages.pdf"));
    const document = await (await uploaded).json();
    expect(document.page_count).toBeGreaterThanOrEqual(2);
    await page.getByLabel("เลือกหน้า PDF").selectOption("2");
    await expect(page.getByAltText("เอกสารที่อัปโหลด")).toBeVisible();
    const batch = await request.post(`${api}/api/documents/${document.id}/run-pages`, { data: { pages: [1, 2], pipelines: [pipeline.pipeline_id] } });
    expect(batch.status()).toBe(200);
    const events = (await batch.text()).trim().split("\n").map(s => JSON.parse(s));
    expect(events.filter(e => e.event === "page_success" || e.event === "page_error").map(e => e.status)).toEqual(["success", "success"]);
    const history = await (await request.get(`${api}/api/history?document=${document.id}&view=summary&latest=true`)).json();
    expect(history).toHaveLength(2);
    const selected = history.find((c: TestCase) => c.page_number === 2);
    const root = `${api}/api/test-cases/${selected.id}`;
    expect((await request.put(`${root}/ground-truth`, { data: { ground_truth_raw: "กำลัง ทดสอบ ภาษาไทย", confirmed: true } })).status()).toBe(200);
    const detail = await (await request.get(root)).json();
    expect(detail.runs[0].metrics.cer).not.toBeNull();
    const zip = await request.post(`${api}/api/dataset/export`, { data: { test_case_ids: [selected.id] } });
    expect(zip.status()).toBe(200);
    const archive = await zip.body();
    expect(archive.subarray(0, 2).toString()).toBe("PK");
    const python = path.resolve(process.platform === "win32" ? "../backend/.venv/Scripts/python.exe" : "../backend/.venv/bin/python");
    const inspected = spawnSync(python, ["-c", "import sys,io,json; from zipfile import ZipFile; from PIL import Image; z=ZipFile(io.BytesIO(sys.stdin.buffer.read())); assert z.testzip() is None; image=Image.open(io.BytesIO(z.read('dataset/images/000001.png'))); print(json.dumps({'label':z.read('dataset/label.txt').decode('utf-8'),'size':image.size}))"], { input: archive });
    expect(inspected.status).toBe(0);
    const contents = JSON.parse(inspected.stdout.toString());
    expect(contents.label).toBe("images/000001.png\tกำลัง ทดสอบ ภาษาไทย\n");
    expect(contents.size).toEqual([selected.document.width, selected.document.height]);
    const edited = await request.put(`${api}/api/pipelines/${pipeline.pipeline_id}/definition`, { data: { ...definitions[0], name: "Network smoke renamed" } });
    expect(edited.status()).toBe(200);
    const refreshed = await (await request.get(`${api}/api/pipelines?fresh=true`)).json();
    expect(refreshed.find((p: { pipeline_id: string }) => p.pipeline_id === pipeline.pipeline_id).name).toBe("Network smoke renamed");
  } finally {
    expect((await request.delete(`${api}/api/pipelines/${pipeline.pipeline_id}`)).status()).toBe(204);
  }
});
