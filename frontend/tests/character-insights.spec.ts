import {test,expect} from "@playwright/test";

const roi={x1:10,y1:20,x2:210,y2:120};
const stats={character_edits:1,substitution:0,deletion:1,insertion:0,gt_characters:2,characters:[{character:"้",display:"◌้",code_point:"U+0E49",name:"ไม้โท",total:1,substitution:0,deletion:1,insertion:0}],confusion_pairs:[]};
const scope={field_id:"ocr-field",global_field_id:"field",field_index:1,roi,state:"ready",statistics:stats,details:[{error_type:"deletion",ground_truth_unit:"้",ocr_unit:null,ground_truth_excerpt:"ก้",ocr_excerpt:"ก",line_number:1}],details_truncated:false};
const insight={document_id:"doc",page_number:2,filename:"synthetic.pdf",test_case_id:"insights",evaluation_mode:"per_field",pipelines:[{pipeline_id:"p1",pipeline_name:"Pipeline One",statistics:stats,scopes:[scope],evaluated_scopes:1,total_scopes:1}]};
const evaluation={cer:.5,wer:1,exact_match:false,character_edits:1,word_edits:1,gt_characters:2,gt_words:1,normalized_ocr:"ก",normalized_ground_truth:"ก้",spans:[{kind:"equal",text:"ก"},{kind:"deletion",text:"",missing:"้"}]};
const record={id:"insights",workflow:"global",categories:[],history_status:"success",has_ground_truth:true,created_at:"2026-10-01T00:00:00Z",ground_truth_raw:"ก้",evaluation_mode:"per_field",layout_confirmed_at:"2026-10-01",global_fields:[{id:"field",field_index:1,roi,source:"manual",ground_truth_raw:"ก้",confirmed_at:"2026-10-01"}],page_number:2,document:{id:"doc",filename:"synthetic.pdf",document_type:"pdf",page_count:3,width:300,height:200,page_number:2,image_url:"/api/preview.svg"},runs:["p1","hidden"].map(p=>({id:p,pipeline_id:p,pipeline_name:p==="p1"?"Pipeline One":"Hidden Pipeline",status:"success",final_text:"ก",confidence:.9,metrics:{cer:.5,wer:1,exact_match:false},fields:[{id:p+"field",global_field_id:"field",field_index:1,status:"success",ocr_text:"ก",confidence:.9,evaluation}]}))};
const svg='<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"><rect width="1200" height="800" fill="white"/><text x="20" y="40">Synthetic source</text></svg>';

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
 const trigger=page.getByRole("button",{name:"View Errors"}).first();
 await expect(trigger).toBeVisible();expect(details).toHaveLength(0);expect(crops).toHaveLength(0);
 await trigger.click();
 const overlay=page.getByRole("dialog");
 await expect(overlay.getByText("Total Character Edits")).toBeVisible();
 expect(details).toHaveLength(1);expect(new URL(details[0]).searchParams.get("pipeline_id")).toBe("p1");
 await overlay.getByRole("button",{name:/ไม้โท: 1/}).click();
 await expect(overlay.getByText("GT: ก้",{exact:true})).toBeVisible();
 await overlay.getByRole("button",{name:"ดูภาพต้นฉบับ (Field Crop)"}).click();
 const crop=page.getByRole("dialog",{name:"Field Crop — ภาพต้นฉบับตาม ROI"});
 await expect(crop.getByAltText("Original Field Crop")).toBeVisible();
 await expect.poll(()=>crops.length).toBe(1);
 const url=new URL(crops[0]);expect(url.searchParams.get("page_number")).toBe("2");
 for(const [key,value]of Object.entries(roi))expect(url.searchParams.get(key)).toBe(String(value));
 const before=await crop.getByLabel("Zoom level").textContent();await crop.getByRole("button",{name:"Zoom In",exact:true}).click();
 await expect(crop.getByLabel("Zoom level")).not.toHaveText(before!);
 for(let i=0;i<8;i++)await crop.getByRole("button",{name:"Zoom In",exact:true}).click();
 const pan=crop.getByRole("region",{name:"Crop image pan"}),box=(await pan.boundingBox())!;
 await page.mouse.move(box.x+box.width*.8,box.y+200);await page.mouse.down();await page.mouse.move(box.x+30,box.y+40,{steps:8});await page.mouse.up();
 expect(await pan.evaluate(e=>e.scrollLeft+e.scrollTop)).toBeGreaterThan(0);
 await crop.getByRole("button",{name:"Fit",exact:true}).click();
 expect(await pan.evaluate(e=>e.scrollLeft+e.scrollTop)).toBe(0);
 const fitZoom=await crop.getByLabel("Zoom level").textContent();
 await pan.hover();await page.keyboard.down("Control");await page.mouse.wheel(0,-100);await page.keyboard.up("Control");
 await expect(crop.getByLabel("Zoom level")).not.toHaveText(fitZoom!);
 await crop.getByRole("button",{name:"ดูเอกสารต้นฉบับ"}).click();
 await expect(page.getByLabel("Global Field region")).toBeVisible();
 expect(crops.some(u=>u.includes("/pages/2/image"))).toBe(true);
 await page.keyboard.press("Escape");await expect(page.getByRole("dialog")).toHaveCount(1);
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
 const download=page.waitForEvent("download");await page.getByRole("button",{name:"Export Evaluation Report",exact:true}).click();await download;
 await page.getByRole("button",{name:"กลับไปแก้ Ground Truth"}).click();
 await page.getByLabel("Ground Truth Field 01",{exact:true}).fill("Changed");
 await page.getByRole("button",{name:"บันทึก GT ฉบับร่าง",exact:true}).click();
 await expect(page.getByRole("button",{name:/ไม้โท: 1/})).toHaveCount(0);
});
