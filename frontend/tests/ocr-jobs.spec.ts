import {test,expect,type APIRequestContext} from "@playwright/test";
import {readFileSync} from "node:fs";
import {randomUUID} from "node:crypto";

const api=process.env.E2E_API_URL||"http://127.0.0.1:8100";
const createdPipelines:string[]=[];
test.afterEach(async({request})=>{for(const id of createdPipelines.splice(0))expect((await request.delete(api+`/api/pipelines/${id}`)).status()).toBe(204);});
async function setup(request:APIRequestContext){
 const created=await request.post(api+"/api/pipelines",{data:{name:"Synthetic durable job "+randomUUID(),source:"custom",execution_mode:"integrated",version:"6",det_weight:"baseline",rec_weight:"thai_ft_v1"}});
 expect(created.status()).toBe(201);const config=await created.json();
 createdPipelines.push(config.pipeline_id);
 const uploaded=await request.post(api+"/api/documents",{multipart:{file:{name:"synthetic-job.png",mimeType:"image/png",buffer:readFileSync("public/sample-document.png")}}});
 expect(uploaded.status()).toBe(201);const doc=await uploaded.json();
 const caseResponse=await request.post(api+"/api/test-cases",{data:{document_id:doc.id,workflow:"global",ground_truth_raw:"synthetic"}});
 expect(caseResponse.status()).toBe(201);const c=await caseResponse.json();
 const field={id:randomUUID(),field_index:1,source:"manual",roi:{x1:20,y1:20,x2:200,y2:100},ground_truth_raw:"synthetic"};
 expect((await request.put(api+`/api/test-cases/${c.id}/global-fields`,{data:{fields:[field],confirmed:true}})).status()).toBe(200);
 return {caseId:c.id,config};
}

test("durable OCR creates one short job, retries status reads and opens persisted results",async({page,request})=>{
 const {caseId,config}=await setup(request);let submissions=0,reads=0;
 page.on("request",r=>{if(r.url().endsWith("/jobs")&&r.method()==="POST")submissions++;});
 await page.route("**/api/ocr-jobs/*",async route=>{reads++;if(reads===1)await route.abort("failed");else await route.continue();});
 await page.goto(`/workflow/${caseId}/pipelines`);
 await expect(page.getByRole("checkbox",{name:`เลือก ${config.name}`,exact:true})).toBeEnabled();
 for(const checkbox of await page.getByTestId("pipeline-options").getByRole("checkbox").all())await checkbox.uncheck();
 await page.getByRole("checkbox",{name:`เลือก ${config.name}`,exact:true}).check();
 const accepted=page.waitForResponse(r=>r.url().endsWith("/jobs")&&r.request().method()==="POST");
 await page.getByRole("button",{name:"Run OCR",exact:true}).click();expect((await accepted).status()).toBe(202);
 await expect(page.getByTestId("ocr-job-progress")).toBeVisible();
 await expect(page.getByText("ไม่สามารถตรวจสอบสถานะได้ชั่วคราว ระบบจะลองเชื่อมต่อเพื่อตรวจสอบงานเดิมอีกครั้ง",{exact:true})).toBeVisible();
 await expect(page).toHaveURL(/ground-truth\?edit=1$/,{timeout:25000});
 expect(submissions).toBe(1);
 const status=await(await request.get(api+`/api/test-cases/${caseId}/jobs`)).json();
 expect(status.status).toBe("completed");expect(status.completed_units).toBe(1);
 const result=await(await request.get(api+`/api/ocr-jobs/${status.job_id}/results`)).json();
 expect(result.runs).toHaveLength(1);expect(result.runs[0].fields).toHaveLength(1);
});

test("durable OCR refresh resumes the accepted job without submitting another run",async({page,request})=>{
 const {caseId,config}=await setup(request);let submissions=0;
 page.on("request",r=>{if(r.url().endsWith("/jobs")&&r.method()==="POST")submissions++;});
 await page.goto(`/workflow/${caseId}/pipelines`);
 await expect(page.getByRole("checkbox",{name:`เลือก ${config.name}`,exact:true})).toBeEnabled();
 for(const checkbox of await page.getByTestId("pipeline-options").getByRole("checkbox").all())await checkbox.uncheck();
 await page.getByRole("checkbox",{name:`เลือก ${config.name}`,exact:true}).check();
 const accepted=page.waitForResponse(r=>r.url().endsWith("/jobs")&&r.request().method()==="POST");
 await page.getByRole("button",{name:"Run OCR",exact:true}).click();const job=await(await accepted).json();
 await expect.poll(()=>page.evaluate(id=>localStorage.getItem(`ocrlab-job:${id}`),caseId)).toBe(job.job_id);
 await page.reload();
 await expect(page).toHaveURL(/ground-truth\?edit=1$/,{timeout:25000});
 expect(submissions).toBe(1);
 const saved=await(await request.get(api+`/api/test-cases/${caseId}`)).json();
 expect(saved.runs).toHaveLength(1);
});

test("job UI fixture: partial success validates saved results then opens GT with warnings without resubmitting",async({page,request})=>{
 const {caseId,config}=await setup(request);
 const prepared=await(await request.post(api+`/api/test-cases/${caseId}/jobs`,{data:{pipelines:[config.pipeline_id],idempotency_key:randomUUID()}})).json();
 await expect.poll(async()=> (await(await request.get(api+`/api/ocr-jobs/${prepared.job_id}`)).json()).status,{timeout:25000}).toBe("completed");
 const persisted=await(await request.get(api+`/api/ocr-jobs/${prepared.job_id}/results`)).json();
 const extra=await request.post(api+"/api/pipelines",{data:{name:"Synthetic partial fixture "+randomUUID(),source:"custom",execution_mode:"integrated",version:"6",det_weight:"baseline",rec_weight:"thai_ft_v1"}});
 expect(extra.status()).toBe(201);const second=await extra.json();createdPipelines.push(second.pipeline_id);
 let submissions=0;
 const fixture={job_id:randomUUID(),test_case_id:caseId,status:"queued",pipeline_ids:[config.pipeline_id,second.pipeline_id],total_fields:1,total_pipelines:2,completed_units:0,failed_units:0,completed_pipelines:0,progress_percent:0,created_at:new Date().toISOString(),started_at:new Date().toISOString(),current_pipeline_id:null,current_field_index:null,run_ids:[],safe_error_message:null};
 await page.route(`**/api/test-cases/${caseId}/jobs`,async route=>{
  if(route.request().method()==="POST"){
   submissions++;expect(route.request().postDataJSON().pipelines.sort()).toEqual([...fixture.pipeline_ids].sort());
   return route.fulfill({status:202,json:fixture});
  }
  return route.fulfill({json:null});
 });
 await page.route(`**/api/ocr-jobs/${fixture.job_id}`,route=>route.fulfill({json:{...fixture,status:"partial_success",completed_units:2,failed_units:1,completed_pipelines:2,progress_percent:100}}));
 await page.route(`**/api/ocr-jobs/${fixture.job_id}/results`,route=>route.fulfill({json:persisted}));
 await page.addInitScript(({key,id})=>sessionStorage.setItem(key,id),{key:`ocrlab-job:${caseId}:opened`,id:prepared.job_id});
 await page.goto(`/workflow/${caseId}/pipelines`);
 await expect(page.getByRole("checkbox",{name:`เลือก ${config.name}`,exact:true})).toBeEnabled();
 for(const checkbox of await page.getByTestId("pipeline-options").getByRole("checkbox").all())await checkbox.uncheck();
 for(const name of [config.name,second.name])await page.getByRole("checkbox",{name:`เลือก ${name}`,exact:true}).check();
 await page.getByRole("button",{name:"Run OCR",exact:true}).click();
 await expect(page).toHaveURL(/ground-truth\?partial=1&edit=1$/);
 await expect(page.getByRole("alert").filter({hasText:"OCR สำเร็จบางส่วน"})).toBeVisible();
 expect(submissions).toBe(1);
});

for(const status of ["failed","cancelled"] as const)test(`terminal ${status} never navigates as success even at 100 percent`,async({page,request})=>{
 const {caseId,config}=await setup(request);let results=0;
 const job={job_id:randomUUID(),test_case_id:caseId,status,progress_percent:100,total_fields:1,total_pipelines:1,completed_units:1,failed_units:1,completed_pipelines:1,created_at:new Date().toISOString(),run_ids:[]};
 await page.route(`**/api/test-cases/${caseId}/jobs`,route=>route.fulfill({json:route.request().method()==="POST"?job:null,status:route.request().method()==="POST"?202:200}));
 await page.route(`**/api/ocr-jobs/${job.job_id}/results`,route=>{results++;return route.fulfill({json:{runs:[]}});});
 await page.goto(`/workflow/${caseId}/pipelines`);
 await expect(page.getByRole("checkbox",{name:`เลือก ${config.name}`,exact:true})).toBeEnabled();
 for(const checkbox of await page.getByTestId("pipeline-options").getByRole("checkbox").all())await checkbox.uncheck();
 await page.getByRole("checkbox",{name:`เลือก ${config.name}`,exact:true}).check();await page.getByRole("button",{name:"Run OCR",exact:true}).click();
 await expect(page.getByTestId("ocr-job-progress")).toContainText(status==="failed"?"งาน OCR ไม่สำเร็จ":"งาน OCR ถูกยกเลิก");
 await expect(page).toHaveURL(/\/pipelines$/);expect(results).toBe(0);
});

test("completed job waits for retrievable persisted results before navigating and keeps its local reference",async({page,request})=>{
 const {caseId,config}=await setup(request);
 const prepared=await(await request.post(api+`/api/test-cases/${caseId}/jobs`,{data:{pipelines:[config.pipeline_id],idempotency_key:randomUUID()}})).json();
 await expect.poll(async()=> (await(await request.get(api+`/api/ocr-jobs/${prepared.job_id}`)).json()).status,{timeout:25000}).toBe("completed");
 let reads=0;
 await page.route(`**/api/ocr-jobs/${prepared.job_id}/results`,route=>{reads++;return reads===1?route.fulfill({status:503,json:{detail:"Temporary results read unavailable"}}):route.continue();});
 await page.goto(`/workflow/${caseId}/pipelines`);
 await expect(page.getByText("ยังโหลดผลที่บันทึกไม่ได้ ระบบจะตรวจสอบงานเดิมอีกครั้ง หรือเปิดผลลัพธ์ด้านล่าง",{exact:true})).toBeVisible();
 await expect(page).toHaveURL(/\/pipelines$/);
 await expect(page).toHaveURL(/ground-truth\?edit=1$/,{timeout:15000});
 expect(await page.evaluate(id=>localStorage.getItem(`ocrlab-job:${id}`),caseId)).toBe(prepared.job_id);
 expect(reads).toBe(2);
});

test("accepted job with lost creation response reuses the same key on manual retry",async({page,request})=>{
 const {caseId,config}=await setup(request);let firstJob="",calls=0;const keys:string[]=[];
 await page.route(`**/api/test-cases/${caseId}/jobs`,async route=>{
  if(route.request().method()!=="POST")return route.continue();
  calls++;keys.push(route.request().postDataJSON().idempotency_key);
  if(calls===1){const response=await route.fetch();expect(response.status()).toBe(202);firstJob=(await response.json()).job_id;return route.abort("failed");}
  return route.continue();
 });
 await page.goto(`/workflow/${caseId}/pipelines`);
 await expect(page.getByRole("checkbox",{name:`เลือก ${config.name}`,exact:true})).toBeEnabled();
 for(const checkbox of await page.getByTestId("pipeline-options").getByRole("checkbox").all())await checkbox.uncheck();
 await page.getByRole("checkbox",{name:`เลือก ${config.name}`,exact:true}).check();
 const start=page.getByRole("button",{name:"Run OCR",exact:true});
 await start.click();await expect(start).toBeEnabled();expect(firstJob).not.toBe("");
 await start.click();await expect(page).toHaveURL(/ground-truth\?edit=1$/,{timeout:25000});
 expect(calls).toBe(2);expect(keys[0]).toBe(keys[1]);
 const saved=await(await request.get(api+`/api/test-cases/${caseId}`)).json();expect(saved.runs).toHaveLength(1);
 const job=await(await request.get(api+`/api/test-cases/${caseId}/jobs`)).json();expect(job.job_id).toBe(firstJob);
});

test("job UI fixture: explicit 404 is shown as missing rather than a transient connection failure",async({page,request})=>{
 const {caseId,config}=await setup(request);const id=randomUUID();let polls=0,submissions=0;
 await page.route(`**/api/test-cases/${caseId}/jobs`,route=>{
  if(route.request().method()==="POST"){submissions++;return route.fulfill({status:202,json:{job_id:id,test_case_id:caseId,status:"queued",pipeline_ids:[config.pipeline_id],total_fields:1,total_pipelines:1,completed_units:0,failed_units:0,completed_pipelines:0,progress_percent:0,created_at:new Date().toISOString(),run_ids:[]}});}
  return route.fulfill({json:null});
 });
 await page.route(`**/api/ocr-jobs/${id}`,route=>{polls++;return route.fulfill({status:404,json:{detail:"OCR job not found"}});});
 await page.goto(`/workflow/${caseId}/pipelines`);
 await expect(page.getByRole("checkbox",{name:`เลือก ${config.name}`,exact:true})).toBeEnabled();
 for(const checkbox of await page.getByTestId("pipeline-options").getByRole("checkbox").all())await checkbox.uncheck();
 await page.getByRole("checkbox",{name:`เลือก ${config.name}`,exact:true}).check();
 await page.getByRole("button",{name:"Run OCR",exact:true}).click();
 await expect(page.getByText("ไม่พบงาน OCR เดิม กรุณาตรวจสอบประวัติ",{exact:true})).toBeVisible();
 await expect(page.getByTestId("ocr-job-progress")).toHaveCount(0);
 expect(polls).toBe(1);expect(submissions).toBe(1);
});
