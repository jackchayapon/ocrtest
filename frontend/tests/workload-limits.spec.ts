import {test,expect} from "@playwright/test";
import {readFileSync} from "node:fs";

const api=process.env.E2E_API_URL||"http://127.0.0.1:8100";

test("upload waits for authoritative limits instead of losing an early selection",async({page})=>{
 let release!:()=>void;
 const gate=new Promise<void>(resolve=>{release=resolve;});
 await page.route("**/api/upload-config",async route=>{await gate;await route.continue();});
 await page.goto("/");
 await expect(page.locator("input[type=file]")).toBeDisabled();
 await expect(page.getByRole("button",{name:"ใช้เอกสารตัวอย่าง",exact:true})).toBeDisabled();
 release();
 await expect(page.locator("input[type=file]")).toBeEnabled();
 const uploaded=page.waitForResponse(r=>r.url().endsWith("/api/documents")&&r.request().method()==="POST");
 await page.locator("input[type=file]").setInputFiles({name:"synthetic-limits-ready.png",mimeType:"image/png",buffer:readFileSync("public/sample-document.png")});
 expect((await uploaded).status()).toBe(201);
 await expect(page.getByAltText("เอกสารที่อัปโหลด")).toBeVisible();
});

test("supported workload is visible and original sample dimensions survive upload",async({page,request})=>{
 const limits=await(await request.get(api+"/api/upload-config")).json();
 expect(limits.max_image_pixels).toBe(2_000_000);expect(limits.max_upload_mb).toBe(10);
 await page.goto("/");
 const notice=page.getByTestId("workload-limits");await expect(notice).toContainText("2 MP");
 await expect(notice).toContainText("20 หน้า");await expect(notice).toContainText("80 Fields และ 3 Pipelines");
 await expect(notice).not.toContainText("ไม่เกิน 24");
 await expect(notice).toContainText("128 DET regions");
 const pending=page.waitForResponse(r=>r.url().endsWith("/api/documents")&&r.request().method()==="POST");
 await page.locator("input[type=file]").setInputFiles({name:"bounded-synthetic.png",mimeType:"image/png",buffer:readFileSync("public/sample-document.png")});
 const response=await pending;expect(response.status()).toBe(201);const doc=await response.json();
 expect(doc.width*doc.height).toBeLessThanOrEqual(limits.max_image_pixels);
 await expect(page.getByAltText("เอกสารที่อัปโหลด")).toBeVisible();
});

test("oversized bodies are rejected without creating a document",async({request})=>{
 const response=await request.post(api+"/api/documents",{
  headers:{"Content-Type":"application/octet-stream"},data:Buffer.alloc(11*1024*1024,0),
 });
 expect(response.status()).toBe(413);expect((await response.json()).detail).toContain("Request body too large");
});
