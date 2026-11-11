import {test,expect} from '@playwright/test';

const record={id:'storage-review',workflow:'global',categories:[],ground_truth_raw:'saved GT',evaluation_mode:'per_field',layout_confirmed_at:'2026-11-08',global_fields:[{id:'f',field_index:1,source:'manual',roi:{x1:1,y1:1,x2:90,y2:90},ground_truth_raw:'saved GT'}],document:{id:'d',filename:'synthetic.png',width:100,height:100,image_url:'/api/synthetic.svg'},runs:[]};
const job={job_id:'storage-job',test_case_id:record.id,status:'running',pipeline_ids:['p'],total_fields:1,total_pipelines:1,completed_units:1,failed_units:0,completed_pipelines:1,progress_percent:100,created_at:'2026-11-08T00:00:00Z',finished_at:'2026-11-08T00:01:00Z',run_ids:['r']};
const runs=[{id:'r',pipeline_id:'p',pipeline_name:'Synthetic',status:'success',final_text:'saved OCR',fields:[{id:'rf',global_field_id:'f',field_index:1,status:'success',ocr_text:'saved OCR'}]}];

for(const mode of ['local-get','local-set','session-get','session-set','all','unavailable','after-start'] as const){
 for(const terminal of ['completed','partial_success'] as const)test(`storage ${mode}: ${terminal} preserves results through refresh/back/recheck`,async({page})=>{
  const errors:string[]=[],keys:string[]=[];let accepted=false,reads=0;
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(mode=>{
   if(mode==='unavailable'){
    for(const name of ['localStorage','sessionStorage'])Object.defineProperty(window,name,{get:()=>{throw new DOMException('Storage unavailable','SecurityError');}});
    return;
   }
   const originals={getItem:Storage.prototype.getItem,setItem:Storage.prototype.setItem,removeItem:Storage.prototype.removeItem};
   for(const method of ['getItem','setItem','removeItem'] as const){
    Object.defineProperty(Storage.prototype,method,{configurable:true,value:function(this:Storage,...args:string[]){
     const blocked=mode==='all'||mode==='after-start'&&(window as unknown as {denyStorage?:boolean}).denyStorage||mode==='local-get'&&this===localStorage&&method==='getItem'||mode==='local-set'&&this===localStorage&&method==='setItem'||mode==='session-get'&&this===sessionStorage&&method==='getItem'||mode==='session-set'&&this===sessionStorage&&method==='setItem';
     if(blocked)throw new DOMException('Synthetic denied storage','SecurityError');
     return Reflect.apply(originals[method],this,args);
    }});
   }
  },mode);
  await page.route('**/api/**',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path.endsWith('/jobs')){
    if(route.request().method()==='POST'){
     keys.push(route.request().postDataJSON().idempotency_key);accepted=true;
     if(mode==='after-start'){
      await page.evaluate(()=>{(window as unknown as {denyStorage:boolean}).denyStorage=true;});
      await page.addInitScript(()=>{(window as unknown as {denyStorage:boolean}).denyStorage=true;});
     }
     return route.fulfill({status:202,json:job});
    }
    return route.fulfill({json:accepted?{...job,status:terminal}:null});
   }
   if(path.endsWith('/results')){reads++;return route.fulfill({json:{runs}});}
   if(path.includes('/ocr-jobs/'))return route.fulfill({json:{...job,status:terminal}});
   if(path.endsWith("/upload-config"))return route.fulfill({json:{max_job_fields:80,max_job_pipelines:3,max_job_units:240}});
   if(path.endsWith('/pipelines'))return route.fulfill({json:[{pipeline_id:'p',name:'Synthetic',enabled:true}]});
   if(path.endsWith('.svg'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>'});
   return route.fulfill({json:{...record,runs:accepted?runs:[]}});
  });
  await page.goto(`/workflow/${record.id}/pipelines`);
  await page.getByRole('button',{name:'Run OCR',exact:true}).click();
  await expect(page).toHaveURL(/ground-truth\?/);
  await expect(page.getByLabel('Ground Truth Field 01',{exact:true})).toHaveValue('saved GT');
  await page.goBack();await expect(page).toHaveURL(/pipelines$/);
  const before=reads;
  await page.getByRole('button',{name:'ตรวจผลอีกครั้ง (ไม่รัน OCR)',exact:true}).click();
  await expect(page).toHaveURL(/ground-truth\?/);expect(reads).toBe(before+1);
  await page.reload();await expect(page.getByLabel('Ground Truth Field 01',{exact:true})).toHaveValue('saved GT');
  await page.goto(`/workflow/${record.id}/pipelines`);await page.reload();
  // Without storage across a full reload, the server job may navigate once again.
  await expect(page.getByLabel('Ground Truth Field 01',{exact:true}).or(page.getByRole('button',{name:'ตรวจผลอีกครั้ง (ไม่รัน OCR)',exact:true}))).toBeVisible();
  expect(keys).toHaveLength(1);expect(errors).toEqual([]);
 });
}

for(const recovery of ['retry','reload'] as const)test(`denied storage recovers ambiguous submission through ${recovery}`,async({page})=>{
 const keys:string[]=[];let returned=false;
 await page.addInitScript(()=>{for(const method of ['getItem','setItem','removeItem'])Object.defineProperty(Storage.prototype,method,{value:()=>{throw new DOMException('Denied','SecurityError');}});});
 await page.route('**/api/**',route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/jobs')){
   if(route.request().method()==='POST'){
    keys.push(route.request().postDataJSON().idempotency_key);
    if(keys.length===1)return route.fulfill({status:503,json:{detail:'Ambiguous response; same key required'}});
    returned=true;return route.fulfill({status:202,json:{...job,status:'completed'}});
   }
   return route.fulfill({json:keys.length?{...job,status:'completed'}:null});
  }
  if(path.endsWith('/results'))return route.fulfill({json:{runs}});
  if(path.endsWith("/upload-config"))return route.fulfill({json:{max_job_fields:80,max_job_pipelines:3,max_job_units:240}});
   if(path.endsWith('/pipelines'))return route.fulfill({json:[{pipeline_id:'p',name:'Synthetic',enabled:true}]});
  if(path.endsWith('.svg'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>'});
  return route.fulfill({json:{...record,runs:returned||keys.length?runs:[]}});
 });
 await page.goto(`/workflow/${record.id}/pipelines`);
 const submit=page.getByRole('button',{name:'Run OCR',exact:true});await submit.click();
 await expect(page.getByRole('region',{name:'สถานะงาน OCR',exact:true}).getByRole('alert')).toBeVisible();await expect(submit).toBeEnabled();
 if(recovery==='retry')await submit.click();else await page.reload();
 await expect(page).toHaveURL(/ground-truth\?/);
 expect(keys).toHaveLength(recovery==='retry'?2:1);if(recovery==='retry')expect(keys[0]).toBe(keys[1]);
});
