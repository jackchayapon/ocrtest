import { test, expect } from "@playwright/test";
import path from "node:path";
import { createHash, randomUUID } from "node:crypto";
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


for (const input of [
  { filename: "tests/fixtures/sample-document.jpg", page: null },
  { filename: "tests/fixtures/two-pages.pdf", page: 2 },
]) {
  test(`release-critical real backend: ${input.filename}, manual page crop, repeated GT and dataset exclusion`, async ({ page, request }) => {
    test.setTimeout(90_000);
    const created = await request.post(`${api}/api/pipelines`, { data: definitions[0] });
    expect(created.status()).toBe(201);
    const pipeline = await created.json();
    try {
      await page.goto("/");
      const uploaded = page.waitForResponse(r => r.url().endsWith("/api/documents") && r.request().method() === "POST");
      await page.locator("input[type=file]").setInputFiles(path.resolve(input.filename));
      const document = await (await uploaded).json();
      if (input.page) await page.getByLabel("เลือกหน้า PDF").selectOption(String(input.page));
      await expect(page.getByAltText("เอกสารที่อัปโหลด")).toBeVisible();
      const prepared = await request.post(`${api}/api/test-cases`, { data: { document_id: document.id, workflow: "global", page_number: input.page } });
      expect(prepared.status()).toBe(201);
      const testCase = await prepared.json();
      const root = `${api}/api/test-cases/${testCase.id}`;
      const fieldId = randomUUID();
      const roi = { x1: 40, y1: 30, x2: 270, y2: 150 };
      const layout = await request.put(`${root}/global-fields`, { data: { confirmed: true, fields: [{ id: fieldId, field_index: 1, source: "manual", roi }] } });
      expect(layout.status()).toBe(200);
      await page.goto(`/workflow/${testCase.id}/pipelines`);
      const options = page.getByTestId("pipeline-options");
      const registry = await (await request.get(`${api}/api/pipelines?fresh=true`)).json();
      await expect(options.getByRole("checkbox")).toHaveCount(registry.length);
      for (const checkbox of await options.getByRole("checkbox").all()) if (await checkbox.isEnabled()) await checkbox.uncheck();
      await options.getByRole("checkbox", { name: `เลือก ${pipeline.name}`, exact: true }).check();
      const completed = page.waitForResponse(r => r.url().endsWith("/run") && r.request().method() === "POST");
      await page.getByRole("button", { name: "Run OCR", exact: true }).click();
      const result = await (await completed).json();
      expect(result.runs).toHaveLength(1);
      expect(result.runs[0].status).toBe("success");
      expect(result.runs[0].fields).toHaveLength(1);
      expect(result.runs[0].fields[0].geometry.roi).toEqual(roi);
      expect(result.runs[0].fields[0].diagnostics.boxes.length).toBeGreaterThan(0);
      expect(result.runs[0].fields[0].diagnostics.boxes[0].bbox).toHaveLength(4);
      const prediction = result.runs[0].fields[0].ocr_text;
      expect(prediction.length).toBeGreaterThan(0);
      const originalFieldId = result.runs[0].fields[0].id;
      for (const gt of [prediction + " กำลัง", prediction.normalize("NFD")]) {
        expect((await request.put(`${root}/global-fields/${fieldId}/ground-truth`, { data: { ground_truth_raw: gt } })).status()).toBe(200);
        const evaluated = await request.post(`${root}/evaluate`, { data: { mode: "per_field", global_field_ids: [fieldId] } });
        expect(evaluated.status()).toBe(200);
        const saved = await (await request.get(root)).json();
        expect(saved.global_fields).toHaveLength(1);
        expect(saved.runs[0].fields).toHaveLength(1);
        expect(saved.runs[0].fields[0].id).toBe(originalFieldId);
        expect(saved.runs[0].fields[0].evaluation.exact_match).toBe(gt === prediction.normalize("NFD"));
      }
      const label = "กำลัง ทดสอบ ภาษาไทย";
      expect((await request.put(`${root}/global-fields/${fieldId}/ground-truth`, { data: { ground_truth_raw: label } })).status()).toBe(200);
      expect((await request.post(`${root}/evaluate`, { data: { mode: "per_field", global_field_ids: [fieldId] } })).status()).toBe(200);
      expect((await request.put(`${root}/ground-truth`, { data: { ground_truth_raw: prediction } })).status()).toBe(200);
      expect((await request.post(`${root}/evaluate`, { data: { mode: "whole_document" } })).status()).toBe(200);
      const detail = await (await request.get(root)).json();
      expect(detail.page_number).toBe(input.page);
      expect(detail.runs[0].document_evaluation.exact_match).toBe(true);
      expect(detail.runs[0].fields[0].evaluation).toBeTruthy();
      const cropQuery = new URLSearchParams(Object.entries(roi).map(([k,v]) => [k,String(v)]));
      if (input.page) cropQuery.set("page_number", String(input.page));
      const crop = await request.get(`${api}/api/documents/${document.id}/crop?${cropQuery}`);
      expect(crop.status()).toBe(200);
      const cropHash = createHash("sha256").update(await crop.body()).digest("hex");
      expect(result.runs[0].fields[0].diagnostics.crop_sha256).toBe(cropHash);
      const exported = await request.post(`${api}/api/dataset/export`, { data: { global_field_ids: [fieldId] } });
      expect(exported.status()).toBe(200);
      const python = path.resolve(process.platform === "win32" ? "../backend/.venv/Scripts/python.exe" : "../backend/.venv/bin/python");
      const inspected = spawnSync(python, ["-c", "import sys,io,json,hashlib; from zipfile import ZipFile; from PIL import Image; z=ZipFile(io.BytesIO(sys.stdin.buffer.read())); assert z.testzip() is None; b=z.read('dataset/images/000001.png'); print(json.dumps({'files':sorted(z.namelist()),'label':z.read('dataset/label.txt').decode('utf-8'),'hash':hashlib.sha256(b).hexdigest(),'size':Image.open(io.BytesIO(b)).size}))"], { input: await exported.body() });
      expect(inspected.status).toBe(0);
      const contents = JSON.parse(inspected.stdout.toString());
      expect(contents.files).toEqual(["dataset/images/000001.png", "dataset/label.txt"]);
      expect(contents.label).toBe(`images/000001.png\t${label}\n`);
      expect(contents.hash).toBe(cropHash);
      expect(contents.size).toEqual([230,120]);
      const excluded = await request.post(`${api}/api/dataset/items/bulk-exclude`, { data: { global_field_ids: [fieldId] } });
      expect(excluded.status()).toBe(200);
      expect((await excluded.json()).excluded).toBe(1);
      const repeated = await request.post(`${api}/api/dataset/items/bulk-exclude`, { data: { global_field_ids: [fieldId] } });
      expect((await repeated.json()).already_excluded).toBe(1);
      expect((await request.post(`${api}/api/dataset/export`, { data: { global_field_ids: [fieldId] } })).status()).toBe(422);
      expect((await (await request.get(root)).json()).runs[0].status).toBe("success");
      const denied = await request.fetch(`${api}/api/documents`, { method: "OPTIONS", headers: { Origin: "https://unapproved.example", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type" } });
      expect(denied.status()).toBe(400);
      expect(denied.headers()["access-control-allow-origin"]).toBeUndefined();
    } finally {
      expect((await request.delete(`${api}/api/pipelines/${pipeline.pipeline_id}`)).status()).toBe(204);
    }
  });
}
