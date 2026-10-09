import { test, expect, type Page } from "@playwright/test";

async function setup(page: Page, groundTruth = false) {
  const record = {
    id: "selection-test", workflow: "global", categories: [], ground_truth_raw: "", evaluation_mode: "per_field",
    layout_confirmed_at: groundTruth ? "2026-10-04" : null, layout_locked_at: null,
    document: { id: "doc", filename: "selection.png", width: 300, height: 200, image_url: "/api/preview.svg", page_number: 1 },
    global_fields: [
      { id: "field-a", field_index: 1, roi: { x1: 20, y1: 20, x2: 120, y2: 70 }, source: "manual", ground_truth_raw: "", confirmed_at: null },
      { id: "field-b", field_index: 2, roi: { x1: 160, y1: 110, x2: 270, y2: 170 }, source: "manual", ground_truth_raw: "", confirmed_at: null },
    ],
    runs: groundTruth ? [{ id: "run", pipeline_id: "mint", pipeline_name: "Mint", status: "success", fields: [], final_text: "OCR" }] : [],
  };
  const state = { failSave: false, drafts: 0, evaluations: 0, confirmations: 0, gtSaves: 0 };
  await page.route("**/api/**", async route => {
    const req = route.request(), url = new URL(req.url()).pathname;
    if (url.endsWith("preview.svg")) return route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200"><rect width="300" height="200" fill="white"/><text x="30" y="50">First field</text><text x="170" y="140">Second field</text></svg>' });
    if (url.endsWith("/pipelines")) return route.fulfill({ json: [{ pipeline_id: "mint", name: "Mint", enabled: true }] });
    if (url.endsWith("/global-fields") && req.method() === "PUT") {
      if (state.failSave) return route.fulfill({ status: 503, json: { detail: "Save failed" } });
      const data = req.postDataJSON();
      record.global_fields = data.fields.map((f: typeof record.global_fields[number]) => ({ ...f, ground_truth_raw: "", confirmed_at: null }));
      record.layout_confirmed_at = data.confirmed ? "2026-10-04" : null;
      if (data.confirmed) state.confirmations++; else state.drafts++;
    }
    if (url.includes("/global-fields/") && url.endsWith("/ground-truth")) {
      const field = record.global_fields.find(f => url.includes(f.id))!;
      field.ground_truth_raw = req.postDataJSON().ground_truth_raw;
      state.gtSaves++;
    }
    if (!url.includes("/global-fields/") && url.endsWith("/ground-truth")) record.ground_truth_raw = req.postDataJSON().ground_truth_raw;
    if (url.endsWith("/evaluate")) {
      expect(req.postDataJSON().require_complete_gt).toBe(true);
      expect(req.postDataJSON().global_field_ids).toEqual(record.global_fields.map(f=>f.id));
      state.evaluations++;
    }
    return route.fulfill({ json: record });
  });
  await page.goto(`/workflow/selection-test/${groundTruth ? "ground-truth" : "layout"}`);
  await expect(page.getByTestId("global-field-nav")).toHaveCount(groundTruth ? 0 : 2);
  await expect(page.getByTestId("document-viewer").locator("canvas").first()).toBeVisible();
  return { record, state };
}

async function clickFrame(page: Page, x: number, y: number) {
  const canvas = page.getByTestId("document-viewer").locator(".konvajs-content");
  await canvas.scrollIntoViewIfNeeded();
  const box = (await canvas.boundingBox())!;
  const scale = Number(await page.getByTestId("document-viewer").getAttribute("data-view-scale"));
  await page.mouse.click(box.x + (box.width - 300 * scale) / 2 + x * scale, box.y + (box.height - 200 * scale) / 2 + y * scale);
}

test("layout can hide other frames and reveal the selected row in a long list",async({page})=>{
 const {record}=await setup(page);
 record.global_fields=Array.from({length:25},(_,i)=>({...record.global_fields[0],id:`field-${i}`,field_index:i+1,
   roi:i===24?{x1:220,y1:180,x2:280,y2:195}:{x1:20,y1:20,x2:120,y2:70}}));
 await page.reload();
 const viewer=page.getByTestId("document-viewer"),list=page.getByRole("region",{name:"Global Fields",exact:true});
 await expect(page.getByTestId("global-field-nav")).toHaveCount(25);
 const previewBounds=await viewer.boundingBox();
 const controlsBounds=await page.getByTestId("controls-column").boundingBox();
 expect(Math.abs(previewBounds!.height-controlsBounds!.height)).toBeLessThan(2);
 expect(Math.abs(previewBounds!.y-controlsBounds!.y)).toBeLessThan(2);
 await viewer.getByRole("button",{name:"แสดงกรอบ Global ทั้งหมด",exact:true}).click();
 await expect(viewer).toHaveAttribute("data-show-all-fields","false");
 await clickFrame(page,250,187);
 const selected=page.getByTestId("global-field-nav").last();
 await expect(selected).toHaveAttribute("aria-pressed","true");
 await expect.poll(()=>list.evaluate(el=>el.scrollTop)).toBeGreaterThan(0);
 await expect.poll(async()=>{
   const row=await selected.boundingBox(),container=await list.boundingBox();
   return !!row&&!!container&&row.y>=container.y&&row.y+row.height<=container.y+container.height;
 }).toBe(true);
});

test("returning from pipelines always opens GT editor even with older evaluations",async({page})=>{
 const {record}=await setup(page,true);
 Object.assign(record.runs[0],{document_evaluation:{cer:0,wer:0,exact_match:true}});
 await page.goto("/workflow/selection-test/pipelines");
 await expect(page.getByRole("button",{name:"แสดงกรอบ Global ทั้งหมด",exact:true})).toHaveCount(0);
 await page.getByRole("link",{name:"4. Ground Truth & Evaluation"}).click();
 await expect(page.getByTestId("comparison-scroll")).toHaveCount(0);
 await expect(page.getByLabel("Ground Truth Field 01",{exact:true})).toBeVisible();
 await page.getByRole("link",{name:/3. Pipelines/}).click();
 await page.getByRole("button",{name:"Run OCR",exact:true}).click();
 await expect(page.getByLabel("Ground Truth Field 01",{exact:true})).toBeVisible();
 await expect(page.getByTestId("comparison-scroll")).toHaveCount(0);
});

for(const gt of [false,true])test(`blank preview clears field selection without deleting ROI (${gt?"GT":"layout"})`,async({page})=>{
 const {record}=await setup(page,gt);
 const original=JSON.stringify(record.global_fields);
 const viewer=page.getByTestId("document-viewer");
 await clickFrame(page,50,45);
 await expect(viewer).toHaveAttribute("data-active-field","field-a");
 await clickFrame(page,140,90);
 await expect(viewer).toHaveAttribute("data-active-field","");
 if(!gt){
   await expect(page.getByTestId("global-field-nav")).toHaveCount(2);
   await expect(page.getByTestId("global-field-nav").first()).toHaveAttribute("aria-pressed","false");
 }
 expect(JSON.stringify(record.global_fields)).toBe(original);
 await clickFrame(page,210,140);
 await expect(viewer).toHaveAttribute("data-active-field","field-b");
});

test("GT preview highlights input, keeps hidden fields selectable and supports zoom/pan",async({page})=>{
 await setup(page,true);
 const viewer=page.getByTestId("document-viewer");
 await expect(viewer.getByRole("button",{name:/วาดพื้นที่|ลบพื้นที่|รีเซ็ตมุมมอง|กรอบข้อความ OCR/})).toHaveCount(0);
 const toggle=viewer.getByRole("button",{name:"แสดงกรอบ Global ทั้งหมด",exact:true});
 await expect(toggle).toHaveAttribute("aria-pressed","true");
 await toggle.click();
 await expect(toggle).toHaveAttribute("aria-pressed","false");
 const input=page.getByLabel("Ground Truth Field 02",{exact:true});
 const originalView=await viewer.evaluate(e=>[e.getAttribute("data-view-scale"),e.getAttribute("data-view-x"),e.getAttribute("data-view-y")]);
 await input.fill("Second field text");
 await expect(viewer).toHaveAttribute("data-active-field","field-b");
 expect(await viewer.evaluate(e=>[e.getAttribute("data-view-scale"),e.getAttribute("data-view-x"),e.getAttribute("data-view-y")])).toEqual(originalView);
 const zoom=await viewer.getAttribute("data-view-scale");
 await input.press("End");await input.pressSequentially(" more");
 await expect(viewer).toHaveAttribute("data-view-scale",zoom!);
 await viewer.getByRole("button",{name:"พอดีกับหน้าจอ",exact:true}).click();
 await clickFrame(page,60,40); // The hidden first ROI remains clickable.
 await expect(viewer).toHaveAttribute("data-active-field","field-a");
 await expect(toggle).toHaveAttribute("aria-pressed","false");
 expect(await viewer.evaluate(e=>[e.getAttribute("data-view-scale"),e.getAttribute("data-view-x"),e.getAttribute("data-view-y")])).toEqual(originalView);
 await viewer.getByRole("button",{name:"ซูมกรอบที่เลือก",exact:true}).click();
 await expect.poll(async()=>Number(await viewer.getAttribute("data-view-scale"))).toBeGreaterThan(1);
 await viewer.getByRole("button",{name:"ซูมเข้า",exact:true}).click();
 const scale=Number(await viewer.getAttribute("data-view-scale"));
 await viewer.getByRole("button",{name:"ซูมออก",exact:true}).click();
 await expect.poll(async()=>Number(await viewer.getAttribute("data-view-scale"))).toBeLessThan(scale);
 await viewer.getByRole("button",{name:"เลื่อนเอกสาร",exact:true}).click();
 const canvas=viewer.locator(".konvajs-content");await canvas.scrollIntoViewIfNeeded();const box=(await canvas.boundingBox())!;
 const before=Number(await viewer.getAttribute("data-view-x"));
 await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2-70,box.y+box.height/2-40,{steps:5});await page.mouse.up();
 await expect.poll(async()=>Number(await viewer.getAttribute("data-view-x"))).not.toBe(before);
 await expect(input).toHaveValue("Second field text more");
 const pannedView=await viewer.evaluate(e=>[e.getAttribute("data-view-scale"),e.getAttribute("data-view-x"),e.getAttribute("data-view-y")]);
 await input.click(); // Selection must preserve the user's zoom and pan.
 await expect(viewer).toHaveAttribute("data-active-field","field-b");
 expect(await viewer.evaluate(e=>[e.getAttribute("data-view-scale"),e.getAttribute("data-view-x"),e.getAttribute("data-view-y")])).toEqual(pannedView);
 await toggle.click();await expect(toggle).toHaveAttribute("aria-pressed","true");
 await viewer.getByRole("button",{name:"พอดีกับหน้าจอ",exact:true}).click();
 await page.screenshot({path:"test-results/gt-preview-tools.png",fullPage:true});
});

test("manual drawing stays active across multiple frames until another tool is selected", async ({page})=>{
 await setup(page);
 const viewer=page.getByTestId("document-viewer");
 await page.getByRole("button",{name:"เพิ่มกรอบ Manual",exact:true}).click();
 const canvas=viewer.locator(".konvajs-content");
 await canvas.scrollIntoViewIfNeeded();
 const box=(await canvas.boundingBox())!;
 const scale=Math.min((box.width-64)/300,(box.height-64)/200,1);
 const x=box.x+(box.width-300*scale)/2,y=box.y+(box.height-200*scale)/2;
 for(const [index,top] of [80,150].entries()){
  await page.mouse.move(x+25*scale,y+top*scale);
  await page.mouse.down();await page.mouse.move(x+90*scale,y+(top+20)*scale,{steps:5});await page.mouse.up();
  await expect(page.getByTestId("global-field-nav")).toHaveCount(3+index);
 }
 await viewer.getByRole("button",{name:"เลื่อนเอกสาร",exact:true}).click();
 await page.mouse.move(x+25*scale,y+40*scale);await page.mouse.down();await page.mouse.move(x+90*scale,y+60*scale,{steps:5});await page.mouse.up();
 await expect(page.getByTestId("global-field-nav")).toHaveCount(4);
});

test("per-field X removes only its own field without checkbox selection; drafts and confirmation persist", async ({ page }) => {
  const { record, state } = await setup(page);
  const viewer = page.getByTestId("document-viewer");
  await expect(viewer.getByRole("button", { name: /ลบ|Clear/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^ลบ Field/ })).toHaveCount(2);
  await expect(page.getByRole("checkbox")).toHaveCount(0);
  await page.getByTestId("global-field-nav").nth(1).click();
  await expect(viewer).toContainText("(160, 110)");
  await clickFrame(page, 60, 40);
  await expect(page.getByTestId("global-field-nav").first()).toHaveAttribute("aria-pressed", "true");
  await page.screenshot({ path: "test-results/global-selection-highlight.png", fullPage: true });
  await page.getByTestId("global-field-nav").nth(1).click();
  // Delete the other row, not the currently highlighted field.
  await page.getByRole("button", { name: "ลบ Field 01", exact: true }).click();
  await expect(page.getByTestId("global-field-nav")).toHaveCount(1);
  expect(record.global_fields).toHaveLength(2); // Local deletion until an explicit save.
  state.failSave = true;
  await page.getByRole("button", { name: "บันทึก Layout ฉบับร่าง", exact: true }).click();
  await expect(page.getByTestId("workflow-layout").getByRole("alert")).toBeVisible();
  expect(state.drafts).toBe(0);
  state.failSave = false;
  await page.getByRole("button", { name: "บันทึก Layout ฉบับร่าง", exact: true }).click();
  await expect(page.getByText("บันทึก Layout ฉบับร่างแล้ว — ยังแก้ไขกรอบได้", { exact: true })).toBeVisible();
  expect(record.global_fields[0].id).toBe("field-b");
  await page.reload();
  await expect(page.getByTestId("global-field-nav")).toHaveCount(1);
  await page.screenshot({ path: "test-results/global-selection-layout.png", fullPage: true });
  await page.getByRole("button", { name: "ยืนยัน ROI", exact: true }).click();
  await expect(page).toHaveURL(/\/pipelines$/);
  await expect(page.getByTestId("global-field-nav")).toHaveCount(0);
  await expect(page.getByText("เลือก Field เพื่อดูกรอบและผลลัพธ์", { exact: true })).toHaveCount(0);
  expect(state.confirmations).toBe(1);
  expect(record.layout_confirmed_at).toBeTruthy();
});

test("GT field focus highlights preview; draft saves without evaluation and confirm evaluates", async ({ page }) => {
  const { state } = await setup(page, true);
  await page.getByLabel("Ground Truth Field 01", { exact: true }).fill("First GT");
  await page.getByLabel("Ground Truth Field 02", { exact: true }).fill("Edited GT");
  await expect(page.getByTestId("document-viewer")).toContainText("(160, 110)");
  await expect(page.getByText("เลือก Field เพื่อดูกรอบและผลลัพธ์", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "บันทึก GT ฉบับร่าง", exact: true }).click();
  await expect(page.getByText("บันทึก GT ฉบับร่างแล้ว — ยังไม่ได้คำนวณผลประเมิน", { exact: true })).toBeVisible();
  expect(state.gtSaves).toBe(2);
  expect(state.evaluations).toBe(0);
  await page.getByRole("button", { name: "ยืนยันเพื่อคำนวณ", exact: true }).click();
  await expect(page.getByText("คำนวณแล้ว — ผลประเมินอยู่ในตาราง", { exact: true })).toBeVisible();
  expect(state.evaluations).toBe(1);
  await expect(page.getByTestId("comparison-scroll")).toBeVisible();
  await expect(page.getByTestId("document-viewer")).toHaveCount(0);
  await page.getByRole("button", { name: "กลับไปแก้ Ground Truth" }).click();
  await page.getByLabel("Ground Truth Field 02", { exact: true }).fill("New draft");
  expect(state.evaluations).toBe(1);
  await expect(page.getByText("คำนวณแล้ว — ผลประเมินอยู่ในตาราง", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: "test-results/global-selection-gt.png", fullPage: true });
});

test("GT synchronizes both modes, supports multiline ROI boundaries and requires every field", async ({page})=>{
 const {state,record}=await setup(page,true);
 const ocrRequests:string[]=[];
 page.on("request",request=>{if(new URL(request.url()).pathname.endsWith("/run"))ocrRequests.push(request.url());});
 const confirm=page.getByRole("button",{name:"ยืนยันเพื่อคำนวณ",exact:true});
 await expect(confirm).toBeDisabled();
 await page.getByRole("button",{name:"Whole Field",exact:true}).click();
 await expect(page.getByRole("spinbutton")).toHaveCount(0);
 await page.getByLabel("เพิ่ม Field ที่มีหลายบรรทัด",{exact:true}).selectOption("field-a");
 await expect(page.getByLabel("จำนวนบรรทัด Field 01")).toHaveValue("2");
 await page.getByRole("button",{name:"คืนค่า Field 01 เป็น 1 บรรทัด",exact:true}).click();
 await expect(page.getByRole("spinbutton")).toHaveCount(0);
 await page.getByRole("button",{name:"Sub-fields",exact:true}).click();
 await page.getByLabel("Ground Truth Field 01",{exact:true}).fill("ชื่อ\nนามสกุล");
 await expect(confirm).toBeDisabled();
 await page.getByLabel("Ground Truth Field 02",{exact:true}).fill("ที่อยู่");
 await expect(confirm).toBeEnabled();
 await page.getByRole("button",{name:"Whole Field",exact:true}).click();
 const whole=page.getByLabel("Ground Truth ทั้งเอกสาร",{exact:true});
 await expect(whole).toHaveValue("ชื่อ\nนามสกุล\nที่อยู่");
 await expect(page.getByLabel("จำนวนบรรทัด Field 01")).toHaveValue("2");
 await expect(page.getByTestId("gt-field-preview")).toHaveCount(2);
 await expect(page.getByTestId("gt-field-preview").first()).toContainText("ชื่อ\nนามสกุล");
 await expect(page.getByTestId("gt-field-preview").first().getByRole("button")).toHaveCount(1);
 await whole.fill("ชื่อใหม่\nนามสกุลใหม่\nบ้านเลขที่\nถนน");
 await page.getByRole("button",{name:"Sub-fields",exact:true}).click();
 await expect(page.getByLabel("Ground Truth Field 01",{exact:true})).toHaveValue("ชื่อใหม่\nนามสกุลใหม่");
 await expect(page.getByLabel("Ground Truth Field 02",{exact:true})).toHaveValue("บ้านเลขที่\nถนน");
 await page.getByRole("button",{name:"Whole Field",exact:true}).click();
 await page.getByLabel("จำนวนบรรทัด Field 01").fill("3");
 await expect(page.getByTestId("gt-field-preview").first()).toContainText("ชื่อใหม่\nนามสกุลใหม่\nบ้านเลขที่");
 await page.getByRole("button",{name:"ดูกรอบ Field 02",exact:true}).click();
 await expect(page.getByTestId("document-viewer")).toContainText("(160, 110)");
 await whole.fill("บรรทัดเดียว");
 await expect(confirm).toBeDisabled();
 await expect(page.getByTestId("gt-completeness")).toContainText("Field 02");
 await whole.fill("หนึ่ง\nสอง\nสาม\nสี่");
 await expect(confirm).toBeEnabled();
 expect(state.evaluations).toBe(0);
 await page.getByRole("button",{name:"บันทึก GT ฉบับร่าง",exact:true}).click();
 await expect(page.getByText("บันทึก GT ฉบับร่างแล้ว — ยังไม่ได้คำนวณผลประเมิน",{exact:true})).toBeVisible();
 expect(record.global_fields.map(f=>f.ground_truth_raw)).toEqual(["หนึ่ง\nสอง\nสาม","สี่"]);
 expect(record.ground_truth_raw).toBe("หนึ่ง\nสอง\nสาม\nสี่");
 expect(state.evaluations).toBe(0);
 await page.screenshot({path:"test-results/gt-sync.png",fullPage:true});
 await page.reload();
 await page.getByRole("button",{name:"Whole Field",exact:true}).click();
 await expect(page.getByLabel("จำนวนบรรทัด Field 01")).toHaveValue("3");
 await expect(whole).toHaveValue("หนึ่ง\nสอง\nสาม\nสี่");
 await confirm.click();
 await expect(page.getByTestId("comparison-scroll")).toBeVisible();
 expect(state.evaluations).toBe(1);
 expect(ocrRequests).toEqual([]);
});

test("returning to confirmed layout keeps editable frames and revisions preserve existing OCR",async({page})=>{
 const {record}=await setup(page,true);
 record.global_fields[0].ground_truth_raw="First saved GT";
 record.global_fields[1].ground_truth_raw="Second saved GT\nSecond line";
 record.ground_truth_raw="First saved GT\nSecond saved GT\nSecond line";
 await page.reload();
 const original=JSON.stringify(record);
 await page.getByRole("link",{name:/2\. Global Layout/}).click();
 await expect(page.getByTestId("global-field-nav")).toHaveCount(2);
 await expect(page.getByRole("button",{name:"เพิ่มกรอบ Manual",exact:true})).toBeEnabled();
 await expect(page.getByRole("button",{name:"ลบ Field 01",exact:true})).toBeEnabled();
 // Confirming an unchanged historic layout should not create a new case.
 let creates=0;
 const revision={...record,id:"revision",runs:[],global_fields:record.global_fields.map(f=>({...f})),layout_confirmed_at:null as string|null};
 await page.route("**/api/test-cases",async route=>{if(route.request().method()!=="POST")return route.fallback();creates++;return route.fulfill({json:revision});});
 await page.route("**/api/test-cases/revision**",async route=>{
  if(route.request().method()==="PUT"&&route.request().url().endsWith("/global-fields")){
   const data=route.request().postDataJSON();revision.global_fields=data.fields;revision.layout_confirmed_at=data.confirmed?"2026-10-04":null;
  }
  return route.fulfill({json:revision});
 });
 await page.getByRole("button",{name:"ยืนยัน ROI",exact:true}).click();
 await expect(page).toHaveURL(/selection-test\/pipelines$/);expect(creates).toBe(0);
 await page.getByRole("link",{name:/2\. Global Layout/}).click();
 await page.getByRole("button",{name:"ลบ Field 01",exact:true}).click();
 await expect(page.getByTestId("global-field-nav")).toHaveCount(1);
 await page.getByRole("button",{name:"ยืนยัน ROI",exact:true}).click();
 await expect(page).toHaveURL(/revision\/pipelines$/);
 expect(creates).toBe(1);expect(JSON.stringify(record)).toBe(original);
 expect(revision.global_fields).toHaveLength(1);
 expect(revision.global_fields[0].roi).toEqual(record.global_fields[1].roi);
 expect(revision.global_fields[0].id).not.toBe(record.global_fields[1].id);
 expect(revision.global_fields[0].ground_truth_raw).toBe("Second saved GT\nSecond line");
 await page.getByRole("link",{name:/2\. Global Layout/}).click();
 await expect(page.getByTestId("global-field-nav")).toHaveCount(1);
 await expect(page.getByRole("button",{name:"ลบ Field 01",exact:true})).toBeEnabled();
 await page.screenshot({path:"test-results/layout-edit-revision.png",fullPage:true});
});
