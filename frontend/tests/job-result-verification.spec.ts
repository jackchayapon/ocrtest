import {test,expect} from '@playwright/test';

const job={job_id:'00000000-0000-4000-8000-000000000001',test_case_id:'verify',status:'completed',pipeline_ids:['p'],total_fields:1,total_pipelines:1,completed_units:1,failed_units:0,completed_pipelines:1,progress_percent:100,created_at:'2026-11-08T00:00:00Z',run_ids:['r']};
const record={id:'verify',workflow:'global',categories:[],ground_truth_raw:'x',evaluation_mode:'per_field',layout_confirmed_at:'2026-11-08',global_fields:[{id:'f',field_index:1,source:'manual',roi:{x1:1,y1:1,x2:90,y2:90},ground_truth_raw:'x'}],document:{id:'d',filename:'synthetic.png',width:100,height:100,image_url:'/api/synthetic.svg'},runs:[]};

for(const blocked of ['read','write'] as const)test(`GT remains editable when navigation acknowledgement storage blocks ${blocked}`,async({page})=>{
 const errors:string[]=[],mutations:string[]=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(({blocked,jobId})=>{
  const read=Storage.prototype.getItem,write=Storage.prototype.setItem;
  Storage.prototype.getItem=function(key){if(key==='ocrlab-job:verify'){if(blocked==='read')throw new DOMException('Synthetic storage denied','SecurityError');return jobId;}return read.call(this,key);};
  Storage.prototype.setItem=function(key,value){if(blocked==='write'&&key==='ocrlab-job:verify:opened')throw new DOMException('Synthetic storage quota','QuotaExceededError');return write.call(this,key,value);};
 },{blocked,jobId:job.job_id});
 await page.route('**/api/**',route=>{
  const path=new URL(route.request().url()).pathname;
  if(route.request().method()!=='GET')mutations.push(path);
  if(path.endsWith('/pipelines'))return route.fulfill({json:[]});
  if(path.endsWith('.svg'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>'});
  return route.fulfill({json:{...record,runs:[{id:'r',pipeline_id:'p',status:'success',final_text:'x',fields:[]}]}});
 });
 await page.goto('/workflow/verify/ground-truth?edit=1');
 const input=page.getByLabel('Ground Truth Field 01',{exact:true});
 await expect(input).toHaveValue('x');await input.fill('Thai กิ่');await expect(input).toHaveValue('Thai กิ่');
 expect(errors).toEqual([]);expect(mutations).toEqual([]);
});

for(const status of ['completed','partial_success','failed','cancelled'])test(`terminal elapsed time is persisted and frozen: ${status}`,async({page})=>{
 let posts=0;
 await page.clock.install({time:new Date('2026-11-09T00:00:00Z')});
 await page.route('**/api/**',route=>{
  const path=new URL(route.request().url()).pathname;
  if(route.request().method()==='POST')posts++;
  if(path.endsWith('/jobs'))return route.fulfill({json:{...job,status,finished_at:'2026-11-08T00:01:05Z',updated_at:'2026-11-08T00:01:05Z'}});
  if(path.endsWith('/results'))return route.fulfill({status:403,json:{detail:'No automatic navigation in this fixture'}});
  if(path.endsWith('/pipelines'))return route.fulfill({json:[{pipeline_id:'p',name:'Synthetic',enabled:true}]});
  if(path.endsWith('/upload-config'))return route.fulfill({json:{max_upload_mb:10,max_image_pixels:4000000,max_image_dimension:8000,max_pdf_pages:20,pdf_render_dpi:200,max_job_fields:12,max_job_pipelines:6,ocr_queue_capacity:5}});
  if(path.endsWith('.svg'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>'});
  return route.fulfill({json:record});
 });
 await page.goto('/workflow/verify/pipelines');
 const progress=page.getByTestId('ocr-job-progress');
 await expect(progress).toContainText('เวลาที่ผ่านไป: 01:05');
 await page.clock.runFor(120000);await expect(progress).toContainText('เวลาที่ผ่านไป: 01:05');
 await page.reload();await expect(progress).toContainText('เวลาที่ผ่านไป: 01:05');expect(posts).toBe(0);
});

for(const scenario of ['empty-completed','empty-partial','errors','all-failed','forbidden','hanging'] as const){
 test(`terminal results verification: ${scenario}`,async({page})=>{
  let reads=0,posts=0,recover=false;
  await page.clock.install();
  await page.route('**/api/**',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(route.request().method()==='POST'){posts++;return route.fulfill({status:500,json:{detail:'No inference expected'}});}
   if(path.endsWith('/results')){
    reads++;
    if(scenario==='hanging'&&!recover)return; // Leave the fetch pending until the component deadline aborts it.
    if(scenario==='forbidden'&&!recover)return route.fulfill({status:403,json:{detail:'Forbidden'}});
    if(scenario==='errors'&&!recover)return route.fulfill({status:503,json:{detail:'Unavailable'}});
    const available=recover||scenario.startsWith('empty')&&reads>1;
    return route.fulfill({json:{runs:available?[{id:'r',status:'success',fields:[{status:'success'},{status:'error'}]}]:scenario==='all-failed'?[{id:'r',status:'success',fields:[{status:'error'}]}]:[]}});
   }
   if(path.endsWith('/jobs'))return route.fulfill({json:{...job,status:scenario==='empty-partial'?'partial_success':'completed'}});
   if(path.endsWith('/pipelines'))return route.fulfill({json:[{pipeline_id:'p',name:'Synthetic',enabled:true}]});
   if(path.endsWith('.svg'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>'});
   return route.fulfill({json:record});
  });
  await page.goto('/workflow/verify/pipelines');
  await expect.poll(()=>reads).toBe(1);
  if(scenario.startsWith('empty')){
   await expect(page).toHaveURL(/\/pipelines$/);
   await page.clock.runFor(5100);
   await expect(page).toHaveURL(scenario==='empty-partial'?/ground-truth\?partial=1&edit=1$/:/ground-truth\?edit=1$/);
   expect(reads).toBe(2);
  }else{
   if(['errors','all-failed'].includes(scenario))for(let i=2;i<=6;i++){await page.clock.runFor(5100);await expect.poll(()=>reads).toBe(i);}
   if(scenario==='hanging')await page.clock.runFor(30_100);
   const retry=page.getByRole('button',{name:'ตรวจผลอีกครั้ง (ไม่รัน OCR)',exact:true});
   await expect(retry).toBeEnabled();
   await expect(page.getByRole('region',{name:'สถานะงาน OCR'}).getByRole('alert')).toContainText(scenario==='forbidden'?'ไม่สามารถเข้าถึงผล OCR':'หยุดตรวจผลอัตโนมัติ');
   const stopped=reads;await page.clock.runFor(120_000);expect(reads).toBe(stopped);
   await expect(page).toHaveURL(/\/pipelines$/);
   await expect(page.getByRole('button',{name:'รัน OCR ใหม่ (ประมวลผลซ้ำ)',exact:true})).toBeVisible();
   expect(await page.evaluate(()=>localStorage.getItem('ocrlab-job:verify'))).toBe(job.job_id);
   recover=true;await retry.click();await expect(page).toHaveURL(/ground-truth\?edit=1$/);
   expect(reads).toBe(stopped+1);
  }
  expect(posts).toBe(0);
 });
}

test('GT loading failure retains the saved job; reload and back do not submit OCR',async({page})=>{
 let caseReads=0,posts=0;
 await page.route('**/api/**',route=>{
  const path=new URL(route.request().url()).pathname;
  if(route.request().method()==='POST'){posts++;return route.fulfill({status:500,json:{detail:'Unexpected inference'}});}
  if(path.endsWith('/upload-config'))return route.fulfill({json:{max_upload_mb:10,max_image_pixels:4000000,max_image_dimension:8000,max_pdf_pages:20,pdf_render_dpi:200,max_job_fields:12,max_job_pipelines:6,ocr_queue_capacity:5}});
  if(path.endsWith('/results'))return route.fulfill({json:{runs:[{id:'r',status:'success'}]}});
  if(path.endsWith('/jobs'))return route.fulfill({json:job});
  if(path.endsWith('/pipelines'))return route.fulfill({json:[{pipeline_id:'p',name:'Synthetic',enabled:true}]});
  if(path.endsWith('.svg'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>'});
  caseReads++;
  if(caseReads===2)return route.fulfill({status:503,json:{detail:'Synthetic GT data unavailable'}});
  return route.fulfill({json:{...record,runs:[{id:'r',pipeline_id:'p',status:'success',fields:[]}]}});
 });
 await page.goto('/workflow/verify/pipelines');
 await expect(page).toHaveURL(/ground-truth\?edit=1$/);
 await expect(page.getByRole('main').getByRole('alert')).toHaveText('ไม่สามารถดำเนินการได้ กรุณาลองใหม่อีกครั้ง');
 expect(caseReads).toBe(2);
 expect(await page.evaluate(()=>localStorage.getItem('ocrlab-job:verify'))).toBe(job.job_id);
 expect(await page.evaluate(()=>sessionStorage.getItem('ocrlab-job:verify:opened'))).toBeNull();
 await page.reload();
 await expect(page.getByRole('button',{name:'Sub-fields',exact:true})).toBeVisible();
 await expect.poll(()=>page.evaluate(()=>sessionStorage.getItem('ocrlab-job:verify:opened'))).toBe(job.job_id);
 await page.goBack();await expect(page).toHaveURL(/\/pipelines$/);
 await expect(page.getByRole('button',{name:'รัน OCR ใหม่ (ประมวลผลซ้ำ)',exact:true})).toBeEnabled();
 expect(posts).toBe(0);
});
