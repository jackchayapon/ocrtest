import {test,expect} from "@playwright/test";
import {randomUUID} from "node:crypto";
import {readFileSync} from "node:fs";
import sharp from "sharp";
import {t} from "../lib/i18n/th";

const api=process.env.E2E_API_URL||"http://127.0.0.1:8100";
test("38 fields: preview/input focus, missing GT, independent labels and stable zoom",async({page,request})=>{
 const config=await(await request.post(api+"/api/pipelines",{data:{name:"Audit "+randomUUID(),source:"custom",execution_mode:"integrated",version:"6",det_weight:"baseline",rec_weight:"thai_ft_v1"}})).json();
 try{
  const doc=await(await request.post(api+"/api/documents",{multipart:{file:{name:"audit.png",mimeType:"image/png",buffer:readFileSync("public/sample-document.png")}}})).json();
  const c=await(await request.post(api+"/api/test-cases",{data:{document_id:doc.id,workflow:"global",ground_truth_raw:"synthetic disables prefill"}})).json();
  const fields=Array.from({length:38},(_,i)=>({id:randomUUID(),field_index:i+1,source:"manual",ground_truth_raw:i===0?"draft":null,roi:{x1:Math.floor(i%5*doc.width/5+2),y1:Math.floor(Math.floor(i/5)*doc.height/8+2),x2:Math.floor((i%5+1)*doc.width/5-2),y2:Math.floor((Math.floor(i/5)+1)*doc.height/8-2)}}));
  expect((await request.put(api+`/api/test-cases/${c.id}/global-fields`,{data:{fields,confirmed:true}})).status()).toBe(200);
  const job=await(await request.post(api+`/api/test-cases/${c.id}/jobs`,{data:{pipelines:[config.pipeline_id],idempotency_key:randomUUID()}})).json();
  await expect.poll(async()=> (await(await request.get(api+`/api/ocr-jobs/${job.job_id}`)).json()).status,{timeout:45000}).toBe("completed");
  await page.goto(`/workflow/${c.id}/ground-truth?edit=1`);
  const viewer=page.getByTestId("document-viewer");await expect(viewer.locator("canvas").first()).toBeVisible();
  await page.getByRole("button",{name:"Sub-fields",exact:true}).click();
  await expect(page.locator(`[data-field-id="${fields[0].id}"]`)).toHaveAttribute("data-missing-gt","false");
  const missing=page.locator(`[data-field-id="${fields[37].id}"]`);
  const red=await page.evaluate(()=>{const e=document.createElement("div");e.style.borderColor="var(--color-red-500)";document.body.appendChild(e);const color=getComputedStyle(e).borderColor;e.remove();return color;});
  await expect(missing).toHaveCSS("border-color",red);
  const last=page.getByLabel("Ground Truth Field 38",{exact:true});
  const canvas=viewer.locator(".konvajs-content");await canvas.scrollIntoViewIfNeeded();
  const box=await canvas.boundingBox();const scale=Number(await viewer.getAttribute("data-view-scale")),x=Number(await viewer.getAttribute("data-view-x")),y=Number(await viewer.getAttribute("data-view-y")),r=fields[37].roi;
  const scrollBefore=await page.evaluate(()=>window.scrollY);
  await page.mouse.click(box!.x+x+(r.x1+r.x2)*scale/2,box!.y+y+(r.y1+r.y2)*scale/2);
  await expect(last).toBeFocused();expect(await page.evaluate(()=>window.scrollY)).toBe(scrollBefore);
  await expect(missing.getByTestId("missing-gt-indicator")).toBeVisible();
  await last.fill("กิ่ Thai 123");await expect(page.locator(`[data-field-id="${fields[37].id}"]`)).toHaveAttribute("data-missing-gt","false");
  await expect(missing.getByTestId("missing-gt-indicator")).toBeHidden();
  await expect(viewer).toHaveAttribute("data-active-field",fields[37].id);
  // Read actual rendered pixels: hiding a label changes its badge but preserves the outline.
  const sample=async()=>{
   const r=fields[6].roi,s=Number(await viewer.getAttribute('data-view-scale')),vx=Number(await viewer.getAttribute('data-view-x')),vy=Number(await viewer.getAttribute('data-view-y'));
   const png=await canvas.screenshot({scale:'css',animations:'disabled'});
   const px=(left:number,top:number,width:number,height:number)=>sharp(png).extract({left:Math.round(left),top:Math.round(top),width,height}).raw().toBuffer();
   return {label:await px(vx+r.x1*s,vy+r.y1*s-23,65,20),border:await px(vx+r.x1*s-2,vy+(r.y1+r.y2)*s/2,5,12)};
  };
  const labeled=await sample();
  await viewer.getByRole("button",{name:"แสดงชื่อ Field",exact:true}).click();
  await expect(viewer).toHaveAttribute("data-show-field-labels","false");await expect(viewer).toHaveAttribute("data-show-all-fields","true");
  await expect.poll(async()=>(await sample()).label).not.toEqual(labeled.label);
  expect((await sample()).border).toEqual(labeled.border);
  await viewer.getByRole('button',{name:'แสดงกรอบ Global ทั้งหมด',exact:true}).click();
  await expect.poll(async()=>(await sample()).border).not.toEqual(labeled.border);
  await viewer.getByRole('button',{name:'แสดงกรอบ Global ทั้งหมด',exact:true}).click();
  await expect.poll(async()=>(await sample()).border).toEqual(labeled.border);
  await viewer.getByRole("button",{name:t("Zoom in"),exact:true}).click();
  const zoom=await viewer.getAttribute("data-view-scale");
  await page.setViewportSize({width:1180,height:850});await expect(viewer).toHaveAttribute("data-view-scale",zoom!);
  await page.reload();await expect(viewer).toHaveAttribute("data-view-scale",zoom!);
  await viewer.getByRole("button",{name:t("Fit document to view"),exact:true}).click();
  await expect(page.getByRole("button",{name:"เปิด Debug Mode",exact:true})).toHaveCount(0);
  await expect(page.getByTestId("debug-unavailable")).toContainText("ตรวจสิทธิ์");
  await expect(page.getByTestId("safe-debug")).toHaveCount(0);
 }finally{expect((await request.delete(api+`/api/pipelines/${config.pipeline_id}`)).status()).toBe(204);}
});
