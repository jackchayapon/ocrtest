import {test,expect,type Page} from "@playwright/test";
const historyRow=(i:number)=>({id:`h${i}`,workflow:"global",history_status:"success",created_at:"2026-10-06T00:00:00Z",categories:[],ground_truth_raw:"confirmed",document:{id:"d",filename:`sample-${i}.png`,page_count:1},runs:[]});
const sample=(i:number)=>({id:`s${i}`,test_case_id:`h${i}`,global_field_id:i%2?`s${i}`:null,document_id:"d",filename:`sample-${i}.png`,roi:{x1:0,y1:0,x2:100,y2:50},ground_truth_raw:"ยืนยัน",categories:[],source_available:i!==1});
async function mock(page:Page){
 const state={deletions:[] as string[][],exclusions:[] as {test_case_ids:string[];global_field_ids:string[]}[]};
 await page.route("**/api/**",async route=>{
  const req=route.request(),u=new URL(req.url()),p=u.pathname;
  if(req.method()==="OPTIONS")return route.fulfill({status:204});
  if(p==="/api/test-cases/bulk-delete"){const ids=req.postDataJSON().test_case_ids;state.deletions.push(ids);return route.fulfill({json:{requested:ids.length,deleted:ids.length,already_missing:0}});}
  if(p==="/api/dataset/items/bulk-exclude"){const body=req.postDataJSON();state.exclusions.push(body);return route.fulfill({json:{requested:body.test_case_ids.length+body.global_field_ids.length,excluded:body.test_case_ids.length+body.global_field_ids.length,already_excluded:0,not_found:0}});}
  if(p==="/api/history")return route.fulfill({json:Array.from({length:21},(_,i)=>historyRow(Number(u.searchParams.get("offset")||0)+i))});
  if(p==="/api/analytics/summary")return route.fulfill({json:{history_cases:60}});
  if(p==="/api/dataset/samples")return route.fulfill({json:{total:250,items:Array.from({length:50},(_,i)=>sample(Number(u.searchParams.get("offset")||0)+i))}});
  if(p==="/api/document-types")return route.fulfill({json:[{id:"type",name:"บัตร",active:true}]});
  if(p.endsWith("/crop"))return route.fulfill({contentType:"image/svg+xml",body:'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"/>'});
  return route.fulfill({json:[]});
 });return state;
}
for(const width of [1440,390])test(`History bulk visible selection, page retention, cancel and one request ${width}`,async({page})=>{
 const state=await mock(page);await page.setViewportSize({width,height:1000});await page.goto("/history");
 await page.getByLabel("เลือกประวัติ h0",{exact:true}).check();await expect(page.locator("main")).toContainText("เลือกแล้ว 1 รายการ");
 await page.getByRole("button",{name:"ถัดไป",exact:true}).click();await page.getByLabel("เลือกประวัติ h20",{exact:true}).check();await expect(page.locator("main")).toContainText("เลือกแล้ว 2 รายการ");
 await page.getByRole("button",{name:"ลบ 2 รายการ",exact:true}).click();const dialog=page.getByRole("alertdialog");await expect(dialog).toContainText("เอกสารต้นฉบับและชุดทดสอบหน้าอื่น");await page.keyboard.press("Escape");await expect(dialog).not.toBeVisible();expect(state.deletions).toHaveLength(0);
 await page.getByRole("button",{name:"ลบ 2 รายการ",exact:true}).click();await dialog.getByRole("button",{name:"ยืนยันลบ 2 รายการ",exact:true}).click();await expect.poll(()=>state.deletions.length).toBe(1);expect(state.deletions[0]).toEqual(["h0","h20"]);
 await page.getByLabel("เลือกประวัติที่เห็นในหน้านี้ทั้งหมด").check();await expect(page.locator("main")).toContainText("เลือกแล้ว 20 รายการ");await page.getByLabel("ค้นหาในหน้านี้",{exact:true}).fill("sample");await expect(page.getByRole("button",{name:"ลบ 0 รายการ",exact:true})).toBeDisabled();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
});
for(const width of [1440,390])test(`Dataset missing sources, exclusion namespaces and selection limit ${width}`,async({page})=>{
 const state=await mock(page);await page.setViewportSize({width,height:1000});await page.goto("/dataset");await page.getByLabel("เลือก s0",{exact:true}).check();await page.getByLabel("เลือก s1",{exact:true}).check();
 await expect(page.getByLabel("จัดการตัวอย่างที่เลือก")).toContainText("เลือกแล้ว 2 รายการ · พร้อมส่งออก 1");await expect(page.getByRole("button",{name:"ส่งออก ZIP (1 ที่พร้อม)",exact:true})).toBeEnabled();
 await page.getByRole("button",{name:"นำออกจาก Dataset (2)",exact:true}).click();await page.getByRole("alertdialog").getByRole("button",{name:"ยืนยันนำออก 2 รายการ",exact:true}).click();await expect.poll(()=>state.exclusions.length).toBe(1);expect(state.exclusions[0]).toEqual({test_case_ids:["s0"],global_field_ids:["s1"]});
 await expect(page.getByRole("alertdialog")).toBeHidden();
 for(let i=0;i<4;i++){await page.getByLabel(`เลือก s${i*50}`,{exact:true}).waitFor({state:"visible"});await page.getByLabel("เลือกตัวอย่างในหน้านี้ทั้งหมด").check();await expect(page.getByLabel("จัดการตัวอย่างที่เลือก")).toContainText(`เลือกแล้ว ${(i+1)*50} รายการ`);await page.getByRole("button",{name:"ถัดไป",exact:true}).click();await expect(page.getByLabel(`เลือก s${(i+1)*50}`,{exact:true})).toBeVisible();}
 await expect(page.getByLabel("เลือก s200",{exact:true})).toBeDisabled();await page.getByLabel("ประเภทเอกสาร (ธุรกิจ)").selectOption("type");await expect(page.getByLabel("จัดการตัวอย่างที่เลือก")).toContainText("เลือกแล้ว 0 รายการ");
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
});
