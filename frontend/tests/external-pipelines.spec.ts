import {test, expect} from "@playwright/test";

for (const width of [1440, 390]) {
  test(`approved external provider settings, edit and readiness at ${width}px`, async ({page}) => {
    await page.setViewportSize({width, height: 1000});
    const configs: Record<string, unknown>[] = [];
    let checks = 0;
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("**/api/**", async route => {
      const path = new URL(route.request().url()).pathname;
      const method = route.request().method();
      if (path === "/api/external-providers") return route.fulfill({json: []});
      if (path === "/api/pipelines/external-providers") return route.fulfill({json: [{
        id: "openthai", name: "OpenThai 2.0", endpoint: "https://approved.example/api/v1/ocr-text",
        http_method: "POST", request_format: "multipart", image_field: "image",
        response_adapter: "openthai_v1", auth_mode: "bearer", api_key_configured: true,
      }]});
      if (path === "/api/pipelines/models") return route.fulfill({json: []});
      if (path.endsWith("/test-connection")) {
        checks++;
        return route.fulfill({json: {status: "provider_ready", message: "Provider reports ready. Inference has not been tested."}});
      }
      if ((path === "/api/pipelines" && method === "POST") || path.endsWith("/definition")) {
        const body = route.request().postDataJSON();
        expect(body).toMatchObject({source: "external_api", execution_mode: "external_api", provider_id: "openthai", det_model_id: null, rec_model_id: null});
        expect(body.api_key).toBeUndefined();
        expect(body.endpoint).toBeUndefined();
        const value = {...body, pipeline_id: "external-test", id: "external-id", integrated_options: null,
          external_provider: {provider_id: "openthai", provider_name: "OpenThai 2.0", adapter: "openthai_v1", fingerprint: "test"}};
        configs.splice(0, configs.length, value);
        return route.fulfill({status: method === "POST" ? 201 : 200, json: value});
      }
      if (path === "/api/pipelines") return route.fulfill({json: configs});
      return route.fulfill({json: {gateway: "connected", database: {status: "connected"}}});
    });
    await page.goto("/settings/pipelines");
    await page.getByRole("button", {name: "เพิ่ม Pipeline", exact: true}).click();
    await page.getByLabel("Pipeline execution source").selectOption("external");
    await page.getByLabel("การตั้งค่า External API").selectOption("existing");
    await page.getByRole("combobox", {name: "External Provider", exact: true}).selectOption("openthai");
    await page.getByLabel("ชื่อ Pipeline", {exact: true}).fill("OpenThai external");
    await expect(page.getByText("https://approved.example/api/v1/ocr-text", {exact: true})).toBeVisible();
    await expect(page.getByRole("group", {name: "2. Text Detection"})).toHaveCount(0);
    await expect(page.locator('input[type="password"]')).toHaveCount(0);
    await page.getByRole("button", {name: "บันทึก Pipeline", exact: true}).click();
    const card = page.locator("section").filter({has: page.getByRole("heading", {name: "OpenThai external", exact: true})});
    await card.getByRole("button", {name: "Test Connection", exact: true}).click();
    await expect(card.getByText("Provider reports ready. Inference has not been tested.", {exact: true})).toBeVisible();
    expect(checks).toBe(1);
    await card.getByRole("button", {name: "แก้ไข", exact: true}).click();
    await expect(page.getByRole("combobox", {name: "External Provider", exact: true})).toHaveValue("openthai");
    await page.getByLabel("ชื่อ Pipeline", {exact: true}).fill("Renamed external");
    await page.getByLabel("เปิดใช้งานสำหรับทดสอบ OCR", {exact: true}).uncheck();
    await page.getByRole("button", {name: "บันทึก Pipeline", exact: true}).click();
    await page.reload();
    await expect(page.getByRole("heading", {name: "Renamed external", exact: true})).toBeVisible();
    expect(configs[0].enabled).toBe(false);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    expect(errors).toEqual([]);
  });
}

test("external registry failure has a bounded retry and keyboard selection", async ({page}) => {
  let calls = 0;
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/external-providers") return route.fulfill({json: []});
    if (path === "/api/pipelines/external-providers") {
      calls++;
      return route.fulfill(calls === 1 ? {status: 503, json: {detail: "Provider registry unavailable"}} : {json: []});
    }
    return route.fulfill({json: path.endsWith("pipelines") || path.endsWith("models") ? [] : {}});
  });
  await page.goto("/settings/pipelines");
  await page.getByRole("button", {name: "เพิ่ม Pipeline", exact: true}).click();
  const source = page.getByLabel("Pipeline execution source");
  await source.focus();
  await source.press("End");
  await source.press("Enter");
  await expect(source).toHaveValue("external");
  await expect(page.locator('.error-banner[role="alert"]')).toBeVisible();
  await page.getByRole("button", {name: "ลองใหม่", exact: true}).click();
  await expect(page.getByLabel("API Endpoint URL")).toBeEditable();
  expect(calls).toBe(2);
  await expect(page.getByRole("button", {name: "บันทึก Pipeline", exact: true})).toBeEnabled();
});

for (const width of [1440, 390]) {
  test(`public shared API form writes masked keys and invalidates origin at ${width}px`, async ({page}) => {
    await page.setViewportSize({width, height: 1000});
    const provider = {id: "managed_" + "1".repeat(32), name: "Shared test", managed: true,
      endpoint: "https://first.example/ocr", request_format: "multipart", image_field: "image",
      response_adapter: "text_json", auth_mode: "bearer", api_key_configured: true, enabled: true};
    const pipeline = {pipeline_id: "dynamic_" + "2".repeat(32), name: "Shared pipeline", enabled: true,
      source: "external_api", execution_mode: "external_api", external_provider: {provider_id: provider.id, provider_name: provider.name, fingerprint: "one"}};
    let saved = false;
    await page.route("**/api/**", async route => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/external-pipelines") {
        expect(route.request().headers().authorization).toBeUndefined();
        const data = route.request().postDataJSON();
        expect(data).toMatchObject({provider_id: provider.id, pipeline_name: "Shared edited",
          provider: {endpoint: "https://second.example/ocr", credential_action: "replace", api_key: "synthetic-browser-new-key"}});
        expect(data.provider.credential_env).toBeUndefined();
        saved = true;
        return route.fulfill({json: pipeline});
      }
      if (path.endsWith("external-providers")) return route.fulfill({json: [provider]});
      if (path === "/api/pipelines/models") return route.fulfill({json: []});
      if (path === "/api/pipelines") return route.fulfill({json: [pipeline]});
      return route.fulfill({json: {}});
    });
    await page.goto("/settings/pipelines");
    await expect(page.getByText(/Admin Login|เข้าสู่ระบบผู้ดูแล/)).toHaveCount(0);
    const card = page.locator("section").filter({has: page.getByRole("heading", {name: "Shared pipeline", exact: true})});
    await card.getByRole("button", {name: "แก้ไข", exact: true}).click();
    const form = page.getByRole("form", {name: "ตั้งค่า External Pipeline"});
    await expect(form.getByLabel("จัดการ API Key")).toHaveValue("keep");
    await expect(form.locator('input[type="password"]')).toHaveCount(0);
    await form.getByLabel("ชื่อ Pipeline", {exact: true}).fill("Shared edited");
    await form.getByLabel("API Endpoint URL").fill("https://second.example/ocr");
    await expect(form.getByLabel("จัดการ API Key")).toHaveValue("replace");
    const key = form.getByLabel("API Key", {exact: true});
    await expect(key).toHaveAttribute("type", "password");
    await expect(key).toHaveValue("");
    await expect(form.getByRole("option", {name: "ใช้ Key เดิม"})).toHaveCount(0);
    await key.fill("synthetic-browser-new-key");
    await form.getByRole("button", {name: "บันทึก Pipeline", exact: true}).click();
    await expect(form).toHaveCount(0);
    expect(saved).toBe(true);
    expect(await page.evaluate(() => Object.values(localStorage).some(value => String(value).includes("synthetic-browser-new-key")))).toBe(false);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  });
}
