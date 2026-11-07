import {test,expect} from '@playwright/test';

const job={job_id:'00000000-0000-4000-8000-000000000001',test_case_id:'verify',status:'completed',pipeline_ids:['p'],total_fields:1,total_pipelines:1,completed_units:1,failed_units:0,completed_pipelines:1,progress_percent:100,created_at:'2026-11-08T00:00:00Z',run_ids:['r']};
const record={id:'verify',workflow:'global',categories:[],ground_truth_raw:'x',evaluation_mode:'per_field',layout_confirmed_at:'2026-11-08',global_fields:[{id:'f',field_index:1,source:'manual',roi:{x1:1,y1:1,x2:90,y2:90},ground_truth_raw:'x'}],document:{id:'d',filename:'synthetic.png',width:100,height:100,image_url:'/api/synthetic.svg'},runs:[]};

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
