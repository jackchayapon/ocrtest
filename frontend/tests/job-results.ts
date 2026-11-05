import {expect,type Page} from "@playwright/test";

/** Follow the browser's accepted job; never submit a second OCR execution. */
export async function waitForJobResults(page:Page){
 const accepted=await page.waitForResponse(r=>r.url().endsWith("/jobs")&&r.request().method()==="POST");
 expect(accepted.status()).toBe(202);
 const job=await accepted.json();
 const base=new URL(accepted.url()).origin;
 await expect.poll(async()=>{
  const response=await page.request.get(`${base}/api/ocr-jobs/${job.job_id}`);
  expect(response.status()).toBe(200);
  return (await response.json()).status;
 },{timeout:60000,intervals:[250,500,1000]}).not.toMatch(/^(queued|running)$/);
 const results=await page.request.get(`${base}/api/ocr-jobs/${job.job_id}/results`);
 expect(results.status()).toBe(200);
 return results;
}
