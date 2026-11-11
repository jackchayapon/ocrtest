import {expect,type Page} from "@playwright/test";
import {pipelineLabel,t} from "../lib/i18n/th";
import type {PipelineConfig} from "../types";

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

/** Legacy adapter regressions still exercise the complete catalogue, using
 * separate real <=3-Pipeline Jobs. The new 80x3 workflow has its own one-Job tests.
 * Return a real read-only saved-results response, never synthesized OCR results.
 */
export async function runAllConfigured(page:Page){
 const base=process.env.E2E_API_URL||"http://127.0.0.1:8100";
 const configs:PipelineConfig[]=(await(await page.request.get(base+'/api/pipelines')).json()).filter((p:PipelineConfig)=>p.enabled);
 let caseId:string|undefined;
 for(let start=0;start<configs.length;start+=3){
  const group=configs.slice(start,start+3);
  const boxes=page.locator('.pipeline-options input[type=checkbox]');
  await expect(boxes.first()).toBeEnabled();
  for(const checkbox of await boxes.all())if(await checkbox.isEnabled()&&await checkbox.isChecked())await checkbox.uncheck();
  for(const config of group)await page.getByLabel(`เลือก ${pipelineLabel(config.pipeline_id,config.name)}`,{exact:true}).check();
  const pending=waitForJobResults(page);
  await page.getByRole('button',{name:t('Run selected'),exact:true}).click();
  const value=await(await pending).json();
  expect(value.runs.map((r:{pipeline_id:string})=>r.pipeline_id)).toEqual(group.map(p=>p.pipeline_id));
  if(caseId)expect(value.test_case_id).toBe(caseId);
  caseId=value.test_case_id;
 }
 expect(caseId).toBeTruthy();
 await expect(page.getByRole('button',{name:t('Run selected'),exact:true})).toBeEnabled();
 const saved=await page.request.get(`${base}/api/test-cases/${caseId}/results`);
 expect(saved.status()).toBe(200);
 return saved;
}
