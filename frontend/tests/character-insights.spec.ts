import {test,expect} from "@playwright/test";

const roi={x1:10,y1:20,x2:210,y2:120};
const stats={character_edits:1,substitution:0,deletion:1,insertion:0,gt_characters:2,characters:[{character:"้",display:"◌้",code_point:"U+0E49",name:"ไม้โท",total:1,substitution:0,deletion:1,insertion:0}],confusion_pairs:[]};
const scope={field_id:"ocr-field",global_field_id:"field",field_index:1,roi,state:"ready",statistics:stats,details:[{error_type:"deletion",ground_truth_unit:"้",ocr_unit:null,ground_truth_excerpt:"ก้",ocr_excerpt:"ก",line_number:1,explanation:'อ่านขาดหาย "◌้" (ไม้โท) 1 ครั้ง'}],details_truncated:false,explanations:['อ่านขาดหาย "◌้" (ไม้โท) 1 ครั้ง']};
const insight={document_id:"doc",page_number:2,filename:"synthetic.pdf",test_case_id:"insights",evaluation_mode:"per_field",pipelines:[{pipeline_id:"p1",pipeline_name:"Pipeline One",statistics:stats,scopes:[scope],evaluated_scopes:1,total_scopes:1}]};
const evaluation={cer:.5,wer:1,exact_match:false,character_edits:1,word_edits:1,gt_characters:2,gt_words:1,normalized_ocr:"ก",normalized_ground_truth:"ก้",spans:[{kind:"equal",text:"ก"},{kind:"deletion",text:"",missing:"้"}]};
const record={id:"insights",updated_at:"2026-10-01T00:00:00Z",workflow:"global",categories:[],history_status:"success",has_ground_truth:true,created_at:"2026-10-01T00:00:00Z",ground_truth_raw:"ก้",evaluation_mode:"per_field",layout_confirmed_at:"2026-10-01",global_fields:[{id:"field",field_index:1,roi,source:"manual",ground_truth_raw:"ก้",confirmed_at:"2026-10-01"}],page_number:2,document:{id:"doc",filename:"synthetic.pdf",document_type:"pdf",page_count:3,width:300,height:200,page_number:2,image_url:"/api/preview.svg"},runs:["p1","hidden"].map(p=>({id:p,pipeline_id:p,pipeline_name:p==="p1"?"Pipeline One":"Hidden Pipeline",status:"success",document_evaluation:evaluation,final_text:"ก",confidence:.9,metrics:{cer:.5,wer:1,exact_match:false},fields:[{id:p+"field",global_field_id:"field",field_index:1,status:"success",ocr_text:"ก",confidence:.9,evaluation}]}))};
const svg='<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"><rect width="1200" height="800" fill="white"/><text x="20" y="40">Synthetic source</text></svg>';

test("Deep detail opens all field errors and character buttons filter and reset",async({page})=>{
 await page.route("**/api/**",async route=>{
  const url=new URL(route.request().url());
  if(url.pathname.endsWith("preview.svg"))return route.fulfill({contentType:"image/svg+xml",body:svg});
  if(url.pathname.endsWith("/error-summary")){
   const report=structuredClone(insight);
   const second={...scope,global_field_id:"field2",field_id:"ocr2",field_index:2,details:[{...scope.details[0],ground_truth_excerpt:"Second field",explanation:"อ่านจุดผิด"}]};
   report.pipelines[0].scopes=url.searchParams.has("character")?[scope]:[scope,second];
   return route.fulfill({json:report});
  }
  if(url.pathname.endsWith("/pipelines"))return route.fulfill({json:[]});
  return route.fulfill({json:record});
 });
 await page.goto("/workflow/insights/ground-truth");
 await page.getByRole("button",{name:"Error Analysis Pipeline One",exact:true}).click();
 await page.getByRole("checkbox",{name:"Deep detail",exact:true}).check();
 await page.keyboard.press("Escape");
 const summary=page.getByTestId("global-metrics-p1").getByRole("region",{name:"สรุปข้อผิดพลาดในการอ่านตัวอักษร"});
 await expect(summary.getByText("อ่านจุดผิด",{exact:true})).toBeVisible();
 await summary.getByRole("button",{name:/ไม้โท: 1/}).click();
 await expect(summary.getByText("อ่านจุดผิด",{exact:true})).toHaveCount(0);
 await summary.getByRole("button",{name:"แสดงข้อผิดพลาดทั้งหมด",exact:true}).click();
 await expect(summary.getByText("อ่านจุดผิด",{exact:true})).toBeVisible();
 await summary.getByRole("button",{name:/ไม้โท: 1/}).click();
 await expect(summary.getByText("อ่านจุดผิด",{exact:true})).toHaveCount(0);
 await summary.getByRole("button",{name:/ไม้โท: 1/}).click();
 await expect(summary.getByText("อ่านจุดผิด",{exact:true})).toBeVisible();
 await expect(page.getByRole("region",{name:"Error Analysis details",exact:true})).toHaveCount(0);
});

test("detail excerpts highlight extra characters and a missing space at its gap",async({page})=>{
 const report=structuredClone(insight);
 report.pipelines[0].scopes[0].details=[
  {...scope.details[0],ground_truth_unit:" ",ground_truth_excerpt:"Fax: 123",ocr_excerpt:"Fax:123",ground_truth_highlight:{start:4,length:1},ocr_highlight:{start:4,length:0}},
  {...scope.details[0],error_type:"insertion",ground_truth_unit:null,ocr_unit:"๐",ground_truth_excerpt:"😀www.com",ocr_excerpt:"😀www.c๐om",ground_truth_highlight:{start:6,length:0},ocr_highlight:{start:6,length:1}},
 ] as unknown as typeof scope.details;
 await page.route("**/api/**",async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==="/api/history")return route.fulfill({json:[record]});
  if(path.endsWith("/analytics/pipelines"))return route.fulfill({json:record.runs.map(r=>({pipeline_id:r.pipeline_id,pipeline_name:r.pipeline_name}))});
  if(path.endsWith("/error-summary"))return route.fulfill({json:report});
  return route.fulfill({json:[]});
 });
 await page.goto("/history");
 await page.getByRole("button",{name:"ดูข้อผิดพลาด"}).first().click();
 await page.getByRole("button",{name:/ไม้โท: 1/}).click();
 const missing=page.getByText("ข้อความที่ OCR อ่านได้: Fax:[ขาด: ␣]123",{exact:true});
 await expect(missing.locator("mark")).toHaveText("[ขาด: ␣]");
 const extra=page.getByText("ข้อความที่ OCR อ่านได้: 😀www.c[เกิน: ๐]om",{exact:true});
 await expect(extra.locator("mark")).toHaveText("[เกิน: ๐]");
 await expect(page.getByTestId("field-error-ground-truth")).toHaveCount(1);
 await expect(page.getByTestId("field-error-ground-truth").locator("mark")).toHaveCount(0);
});

test("whole document errors share one inline source crop per field",async({page})=>{
 const report=structuredClone(insight);
 const detail={...scope.details[0],source_field:{id:"field",field_index:1,roi}};
 report.pipelines[0].scopes=[{...scope,field_id:null,global_field_id:null,field_index:null,details:[detail,detail]} as unknown as typeof scope];
 await page.route("**/api/**",async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==="/api/history")return route.fulfill({json:[record]});
  if(path.endsWith("/analytics/pipelines"))return route.fulfill({json:record.runs.map(r=>({pipeline_id:r.pipeline_id,pipeline_name:r.pipeline_name}))});
  if(path.endsWith("/error-summary"))return route.fulfill({json:report});
  if(path.endsWith("/crop")){
   expect(new URL(route.request().url()).searchParams.get("x1")).toBe("10");
   return route.fulfill({contentType:"image/svg+xml",body:svg});
  }
  return route.fulfill({json:[]});
 });
 await page.goto("/history");
 await page.getByRole("button",{name:"ดูข้อผิดพลาด"}).first().click();
 await page.getByRole("button",{name:/ไม้โท: 1/}).click();
 await expect(page.getByText("ข้อความจริง (Ground Truth): ก้",{exact:true})).toHaveCount(1);
 const toggle=page.getByRole("button",{name:/Field Crop/});
 await expect(toggle).toHaveCount(1);
 await toggle.click();
 await expect(page.getByAltText("ภาพต้นฉบับของ Field")).toBeVisible();
 await expect(page.getByRole("dialog")).toHaveCount(1);
});

for(const width of [390,1440])test(`lazy history, PDF crop, focus and pan ${width}`,async({page})=>{
 await page.setViewportSize({width,height:900});
 const details:string[]=[],crops:string[]=[];
 await page.route("**/api/**",async route=>{
  const url=new URL(route.request().url());
  if(url.pathname==="/api/history"){
   expect(url.searchParams.get("view")).toBe("summary");expect(url.searchParams.get("latest")).toBe("true");expect(url.searchParams.get("compact")).toBe("true");
   return route.fulfill({json:[record]});
  }
  if(url.pathname.endsWith("/error-summary")){details.push(url.toString());return route.fulfill({json:insight});}
  if(url.pathname.endsWith("/crop")||url.pathname.endsWith("/image")){crops.push(url.toString());return route.fulfill({contentType:"image/svg+xml",body:svg});}
  if(url.pathname.endsWith("/analytics/pipelines"))return route.fulfill({json:record.runs.map(r=>({pipeline_id:r.pipeline_id,pipeline_name:r.pipeline_name}))});
  return route.fulfill({json:[]});
 });
 await page.goto("/history");
 const trigger=page.getByRole("button",{name:"ดูข้อผิดพลาด"}).first();
 await expect(trigger).toBeVisible();expect(details).toHaveLength(0);expect(crops).toHaveLength(0);
 await trigger.click();
 const overlay=page.getByRole("dialog");
 await expect(overlay.getByText("อักขระที่ผิดพลาดทั้งหมด")).toBeVisible();
 expect(new Set(details).size).toBe(1);expect(new URL(details[0]).searchParams.get("pipeline_id")).toBe("p1");
 await overlay.getByRole("button",{name:/ไม้โท: 1/}).click();
 await expect(overlay.getByText("ข้อความจริง (Ground Truth): ก้",{exact:true})).toBeVisible();
 await overlay.getByRole("button",{name:/Field Crop/}).click();
 const crop=page.getByRole("region",{name:"ภาพต้นฉบับตาม ROI ของ Field"});
 await expect(crop.getByAltText("ภาพต้นฉบับของ Field")).toBeVisible();
 await expect.poll(()=>crops.length).toBe(1);
 const url=new URL(crops[0]);expect(url.searchParams.get("page_number")).toBe("2");
 for(const [key,value]of Object.entries(roi))expect(url.searchParams.get(key)).toBe(String(value));
 const before=await crop.getByLabel("ระดับการซูม").textContent();await crop.getByRole("button",{name:"ขยาย",exact:true}).click();
 await expect(crop.getByLabel("ระดับการซูม")).not.toHaveText(before!);
 for(let i=0;i<8;i++)await crop.getByRole("button",{name:"ขยาย",exact:true}).click();
 const pan=crop.getByRole("region",{name:"เลื่อนภาพต้นฉบับ"});
 await pan.scrollIntoViewIfNeeded();
 const box=(await pan.boundingBox())!;
 await page.mouse.move(box.x+box.width*.8,box.y+200);await page.mouse.down();await page.mouse.move(box.x+30,box.y+40,{steps:8});await page.mouse.up();
 expect(await pan.evaluate(e=>e.scrollLeft+e.scrollTop)).toBeGreaterThan(0);
 await crop.getByRole("button",{name:"พอดีหน้าต่าง",exact:true}).click();
 expect(await pan.evaluate(e=>e.scrollLeft+e.scrollTop)).toBe(0);
 const fitZoom=await crop.getByLabel("ระดับการซูม").textContent();
 await pan.hover();await page.keyboard.down("Control");await page.mouse.wheel(0,-100);await page.keyboard.up("Control");
 await expect(crop.getByLabel("ระดับการซูม")).not.toHaveText(fitZoom!);
 await crop.getByRole("button",{name:"ดูเอกสารต้นฉบับ"}).click();
 await expect(page.getByLabel("Global Field region")).toBeVisible();
 expect(crops.some(u=>u.includes("/pages/2/image"))).toBe(true);
 await overlay.getByRole("button",{name:/ซ่อนภาพต้นฉบับ/}).click();await expect(page.getByRole("dialog")).toHaveCount(1);
 await page.keyboard.press("Escape");await expect(page.getByRole("dialog")).toHaveCount(0);
 await expect(trigger).toBeFocused();
});

test("evaluation highlights, lazy characters, hidden export and GT invalidation",async({page})=>{
 const requests:string[]=[];
 const current=structuredClone(record);
 await page.route("**/api/**",async route=>{
  const req=route.request(),url=new URL(req.url());requests.push(url.toString());
  if(url.pathname.endsWith("preview.svg"))return route.fulfill({contentType:"image/svg+xml",body:svg});
  if(url.pathname.endsWith("/error-summary"))return route.fulfill({json:insight});
  if(url.pathname.endsWith("/evaluation-report")){
   expect(url.searchParams.has("pipeline_id")).toBe(false);expect(url.searchParams.get("mode")).toBe("per_field");
   return route.fulfill({contentType:"application/zip",body:Buffer.from("download fixture; real ZIP verified by backend tests")});
  }
  if(url.pathname.includes("/global-fields/")&&url.pathname.endsWith("/ground-truth")){
   current.global_fields[0].ground_truth_raw=req.postDataJSON().ground_truth_raw;
   for(const r of current.runs)r.fields[0].evaluation=null as unknown as typeof evaluation;
  }
  if(url.pathname.endsWith("/pipelines"))return route.fulfill({json:[]});
  return route.fulfill({json:current});
 });
 await page.goto("/workflow/insights/ground-truth");
 const row=page.getByTestId("comparison-row-field");
 await expect(row.getByTestId("highlight-output").first()).toBeVisible();
 expect(requests.filter(u=>u.includes("error-summary"))).toHaveLength(0);
 await page.getByRole("button",{name:"Error Analysis Pipeline One",exact:true}).click();
 await expect(page.getByRole("checkbox",{name:"HIGHLIGHT",exact:true})).toBeChecked();
 await page.getByRole("checkbox",{name:"HIGHLIGHT",exact:true}).uncheck();await page.keyboard.press("Escape");
 await expect(row.getByTestId("global-result-p1").getByTestId("global-prediction")).toHaveText("ก");
 await row.getByRole("button",{name:"ดูสถิติอักขระ"}).first().click();
 await expect(row.getByRole("button",{name:/ไม้โท: 1/})).toBeVisible();
 expect(requests.filter(u=>u.includes("error-summary"))).toHaveLength(1);
 await page.getByRole("button",{name:"กรอง Pipeline",exact:true}).click();
 await page.getByRole("checkbox",{name:"แสดง Hidden Pipeline",exact:true}).uncheck();
 await page.getByRole("button",{name:"ยืนยันตัวกรอง",exact:true}).click();
 await expect(row.getByTestId("global-result-hidden")).toHaveCount(0);
 const download=page.waitForEvent("download");await page.getByTestId("export-menu").locator("summary").click();await page.getByRole("button",{name:"ส่งออกรายงาน ZIP (ทุก Pipeline)",exact:true}).click();await download;
 await page.getByRole("button",{name:"กลับไปแก้ Ground Truth"}).click();
 await page.getByLabel("Ground Truth Field 01",{exact:true}).fill("Changed");
 await page.getByRole("button",{name:"บันทึก GT ฉบับร่าง",exact:true}).click();
 await expect(page.getByRole("button",{name:/ไม้โท: 1/})).toHaveCount(0);
});

for(const width of [390,1440])test("Thai XLSX selection, mode and stale guards "+width,async({page})=>{
 await page.setViewportSize({width,height:1000});
 const current=structuredClone(record),exports:Record<string,unknown>[]=[];
 await page.route("**/api/**",async route=>{
  const req=route.request(),url=new URL(req.url());
  if(url.pathname.endsWith("preview.svg"))return route.fulfill({contentType:"image/svg+xml",body:svg});
  if(url.pathname.endsWith("/pipelines"))return route.fulfill({json:[]});
  if(url.pathname.endsWith("/error-summary"))return route.fulfill({json:insight});
  if(url.pathname.endsWith("/evaluation-excel")){
   exports.push(req.postDataJSON());
   return route.fulfill({contentType:"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",body:Buffer.from("download fixture; real XLSX verified in backend tests")});
  }
  return route.fulfill({json:current});
 });
 await page.goto("/workflow/insights/ground-truth");
 const row=page.getByTestId("comparison-row-field");
 await expect(row.getByRole("region",{name:"สรุปข้อผิดพลาดในการอ่านตัวอักษร"}).first()).toBeVisible();
 await row.getByRole("button",{name:"ดูสถิติอักขระ"}).first().click();
 await expect(row.getByText('อ่านขาดหาย "◌้" (ไม้โท) 1 ครั้ง',{exact:true})).toBeVisible();
 await row.getByRole("button",{name:"ย่อสถิติอักขระ"}).first().click();
 await expect(row.getByRole("region",{name:"สรุปข้อผิดพลาดในการอ่านตัวอักษร"}).first()).not.toContainText("CER");
 await expect(row.getByRole("region",{name:"สรุปข้อผิดพลาดในการอ่านตัวอักษร"}).first()).not.toContainText("WER");
 if(width===1440){
  const modeBox=await page.getByRole("button",{name:"Whole Field",exact:true}).boundingBox();
  const exportBox=await page.getByTestId("export-menu").boundingBox();
  expect(Math.abs(modeBox!.y-exportBox!.y)).toBeLessThan(5);
  expect(exportBox!.x).toBeGreaterThan(modeBox!.x+modeBox!.width);
 }
 await page.getByRole("button",{name:"กรอง Pipeline",exact:true}).click();
 await page.getByRole("checkbox",{name:"แสดง Hidden Pipeline",exact:true}).uncheck();
 await page.getByRole("button",{name:"ยืนยันตัวกรอง",exact:true}).click();
 let download=page.waitForEvent("download");
 await page.getByTestId("export-menu").locator("summary").click();
 await page.getByRole("button",{name:"เอกสารนี้ — Excel (.xlsx)",exact:true}).click();
 expect((await download).suggestedFilename()).toBe("OCRLab_Evaluation.xlsx");
 expect(exports[0]).toEqual({mode:"per_field",pipeline_ids:["p1"],run_ids:["p1"],field_ids:["field"],revision:current.updated_at});
 await page.getByRole("button",{name:"Whole Field",exact:true}).click();
 download=page.waitForEvent("download");
 await page.getByRole("button",{name:"เอกสารนี้ — Excel (.xlsx)",exact:true}).click();await download;
 expect(exports[1].mode).toBe("whole_document");expect(exports[1].field_ids).toEqual([]);
 await page.getByRole("button",{name:"Sub-fields",exact:true}).click();
 current.runs[0].fields[0].evaluation=null as unknown as typeof evaluation;
 await page.reload();
 await page.getByTestId("export-menu").locator("summary").click();
 await expect(page.getByRole("button",{name:"เอกสารนี้ — Excel (.xlsx)",exact:true})).toBeDisabled();
 expect(exports).toHaveLength(2);
});
