import { test, expect, type Page } from "@playwright/test";
import {waitForJobResults} from "./job-results";
import path from "node:path";
import type { TestCase, PipelineRun } from "../types";
const api=process.env.E2E_API_URL||"http://127.0.0.1:8100";
const ids=['mint','hutch_crop','hutch_full','benchmark','thai_ft_v2','hutch_fine_tune_v2'];
async function upload(page:Page,pdf=false){
 await page.goto('/');await expect(page.getByTestId('workflow-upload')).toBeVisible();
 const pending=page.waitForResponse(r=>r.url().endsWith('/api/documents')&&r.request().method()==='POST');
 await page.locator('input[type=file]').setInputFiles(path.resolve(pdf?'tests/fixtures/two-pages.pdf':'public/sample-document.png'));
 const doc=await(await pending).json();await expect(page.getByAltText('เอกสารที่อัปโหลด')).toBeVisible();
 await expect(page.getByRole('button',{name:'Run OCR',exact:true})).toHaveCount(0);await expect(page.locator('textarea')).toHaveCount(0);
 await page.getByRole('button',{name:'ถัดไป: จัดการ Layout',exact:true}).click();await expect(page).toHaveURL(/\/workflow\/[^/]+\/layout$/);await expect(page.getByTestId('document-viewer').locator('canvas').first()).toBeVisible();return doc;
}
async function detect(page:Page){await page.getByRole('button',{name:'Auto Layout',exact:true}).click();await expect(page.getByTestId('global-field-nav')).toHaveCount(3);await expect(page.getByLabel('Auto Layout suggestions')).toHaveCount(0);}
async function confirm(page:Page){
 const pending=page.waitForResponse(r=>r.url().endsWith('/global-fields')&&r.request().method()==='PUT');
 await page.getByRole('button',{name:'ยืนยัน ROI',exact:true}).click();const response=await pending;expect(response.status()).toBe(200);await expect(page).toHaveURL(/\/pipelines$/);await expect(page.getByRole('button',{name:'เพิ่มกรอบ Manual',exact:true})).toHaveCount(0);return await response.json() as TestCase;
}
async function run(page:Page){
 await expect.poll(()=>page.getByTestId('pipeline-options').locator('input:checked').count()).toBeGreaterThan(0);
 const selected=await page.getByTestId('pipeline-options').locator('input:checked').count();
 const pending=waitForJobResults(page);
 await page.getByRole('button',{name:'Run OCR',exact:true}).click();const result=await(await pending).json();
 expect(result.runs).toHaveLength(selected);expect(result.runs.every((r:PipelineRun)=>r.status==='success')).toBeTruthy();
 await expect(page).toHaveURL(/\/ground-truth\?edit=1$/);await expect(page.getByTestId('field-gt-input').first()).toBeVisible();return result;
}
async function draw(page:Page,a:[number,number],b:[number,number]){
 await page.getByRole('button',{name:'เพิ่มกรอบ Manual',exact:true}).click();const viewer=page.getByTestId('document-viewer'),canvas=viewer.locator('.konvajs-content');await canvas.scrollIntoViewIfNeeded();const box=(await canvas.boundingBox())!;
 const scale=Number(await viewer.getAttribute('data-view-scale')),x=box.x+Number(await viewer.getAttribute('data-view-x')),y=box.y+Number(await viewer.getAttribute('data-view-y'));
 await page.mouse.move(x+a[0]*scale,y+a[1]*scale);await page.mouse.down();await page.mouse.move(x+b[0]*scale,y+b[1]*scale,{steps:12});await page.mouse.up();
}
test.beforeEach(async({request})=>{for(const id of ids)expect((await request.put(`${api}/api/pipelines/${id}`,{data:{enabled:true}})).ok()).toBeTruthy();});

test('Hutch fine tune v2 shares four-page workflow, busy state and result blocks with Mint',async({page,request})=>{
 await upload(page);await detect(page);const c=await confirm(page);
 const options=page.getByTestId('pipeline-options');
 await expect(options.getByRole('checkbox',{name:'เลือก Mint Pipeline',exact:true})).toBeVisible();
 for(const box of await options.getByRole('checkbox').all())await box.uncheck();
 await options.getByRole('checkbox',{name:'เลือก Mint Pipeline',exact:true}).check();
 await options.getByRole('checkbox',{name:'เลือก Hutch fine tune v2',exact:true}).check();
 const selected=options.getByRole('checkbox',{name:'เลือก Hutch fine tune v2',exact:true});await expect(selected).toBeChecked();
 let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve;});
 await page.route('**/api/test-cases/*/jobs',async route=>{if(route.request().method()==='POST')await gate;await route.continue();});
 await page.getByRole('button',{name:'Run OCR',exact:true}).click();await expect(selected).toBeDisabled();await expect(page.getByTestId('ocr-spinner')).toBeVisible();release();
 await expect(page).toHaveURL(/\/ground-truth\?edit=1$/);
 for(const n of [1,2,3])await page.getByLabel(`Ground Truth Field 0${n}`).fill('ภาษาไทย');
 await page.getByRole('button',{name:'ยืนยันเพื่อคำนวณ',exact:true}).click();
 const card=page.getByTestId('global-result-hutch_fine_tune_v2').first();await expect(page.getByRole('columnheader').filter({has:page.getByText('Hutch fine tune v2',{exact:true})})).toBeVisible();
 const metrics=page.getByTestId('global-metrics-hutch_fine_tune_v2').first();
 await expect(card.getByRole('region',{name:'Extracted Text',exact:true})).toBeVisible();await expect(metrics.getByRole('region',{name:'Metrics',exact:true})).toBeVisible();
 await expect(metrics.getByTestId('global-evaluation')).toBeVisible();
 await expect(metrics.getByRole('button',{name:'ดูสถิติอักขระ',exact:true})).toBeVisible();
 const saved=await(await request.get(`${api}/api/test-cases/${c.id}`)).json();expect(saved.runs.map((r:PipelineRun)=>r.pipeline_id).sort()).toEqual(['hutch_fine_tune_v2','mint']);
 await page.reload();await expect(page.getByLabel('Ground Truth Field 01')).toHaveValue('ภาษาไทย');
 await page.goto(`/workflow/${c.id}/ground-truth`);await expect(metrics.getByTestId('global-evaluation')).toBeVisible();
});

test('Run OCR shows immediate busy feedback, blocks duplicates and restores after failure',async({page})=>{
 await upload(page);await detect(page);await confirm(page);
 let calls=0,release!:()=>void;
 const gate=new Promise<void>(resolve=>{release=resolve;});
 await page.route('**/api/test-cases/*/jobs',async route=>{if(route.request().method()!=='POST')return route.continue();calls++;await gate;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'OCR service temporarily unavailable'})});});
 await page.getByRole('button',{name:'Run OCR',exact:true}).click();
 const running=page.getByRole('button',{name:'กำลังรัน OCR...',exact:true});
 await expect(running).toBeDisabled();await expect(page.getByTestId('ocr-spinner')).toBeVisible();await expect(page.getByTestId('pipeline-options')).toHaveClass(/opacity-50/);
 for(const checkbox of await page.getByTestId('pipeline-options').getByRole('checkbox').all())await expect(checkbox).toBeDisabled();
 await running.evaluate((button:HTMLButtonElement)=>{button.click();button.click();});expect(calls).toBe(1);
 release();await expect(page.getByRole('button',{name:'Run OCR',exact:true})).toBeEnabled();await expect(page.getByTestId('pipeline-options')).toHaveClass(/opacity-100/);
 for(const checkbox of await page.getByTestId('pipeline-options').getByRole('checkbox').all())await expect(checkbox).toBeEnabled();
 await page.unroute('**/api/test-cases/*/jobs');await run(page);await expect(page.getByTestId('ocr-spinner')).toHaveCount(0);
});

test('GT input cards show focus and synchronize drafts across repeated toggles',async({page})=>{
 await upload(page);await detect(page);await confirm(page);await run(page);
 const sub=page.getByLabel('Ground Truth Field 01',{exact:true});await sub.fill('Sub-field draft');await sub.focus();await expect(sub).toBeFocused();
 await expect(page.getByTestId('field-gt-input').first()).toHaveCSS('border-top-width','1px');
 expect(await sub.evaluate(e=>getComputedStyle(e).boxShadow)).not.toBe('none');
 await page.getByRole('button',{name:'Whole Field',exact:true}).click();const whole=page.getByLabel('Ground Truth ทั้งเอกสาร',{exact:true});await whole.fill('Whole draft');await whole.focus();await expect(whole).toBeFocused();
 await expect(page.getByTestId('whole-gt-card')).toHaveCSS('border-top-width','1px');expect(await whole.evaluate(e=>getComputedStyle(e).boxShadow)).not.toBe('none');
 await page.getByRole('button',{name:'Sub-fields',exact:true}).click();await expect(sub).toHaveValue('Whole draft');await sub.fill('Synced draft');await page.getByRole('button',{name:'Whole Field',exact:true}).click();await expect(whole).toHaveValue(/^Synced draft/);await page.getByRole('button',{name:'Sub-fields',exact:true}).click();await expect(sub).toHaveValue('Synced draft');
});

test('global acceptance: 3 Auto + Manual, shared crops/GT, explicit calculate, History and field Dataset',async({page,request})=>{
 let runCalls=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/jobs'))runCalls++;});
 const doc=await upload(page);expect(runCalls).toBe(0);await expect(page.getByLabel('Ground Truth กลาง')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Run OCR',exact:true})).toHaveCount(0);
 await detect(page);
 await expect(page.getByTestId('global-field-nav')).toHaveCount(3);
 await draw(page,[80,800],[850,930]);await expect(page.getByTestId('global-field-nav')).toHaveCount(4);
 const c=await confirm(page);expect(c.global_fields).toHaveLength(4);expect(c.global_fields?.map(f=>f.source)).toEqual(['auto','auto','auto','manual']);
 expect((await(await request.get(`${api}/api/history?document=${doc.id}`)).json())).toEqual([]);
 const result=await run(page);expect(runCalls).toBe(1);
 const fid=c.global_fields![1].id;
 const predictions=result.runs.map((r:PipelineRun)=>r.fields!.find(f=>f.global_field_id===fid)!);
 expect(new Set(predictions.map((f:{diagnostics:{input_sha256:string}})=>f.diagnostics.input_sha256)).size).toBe(1);
 await expect(page.getByRole('region',{name:'Evaluation Results',exact:true})).toHaveCount(0);
 for(const n of [1,3,4])await page.getByLabel(`Ground Truth Field ${String(n).padStart(2,'0')}`,{exact:true}).fill('บริษัท ซีดีจี จำกัด\nABCD');
 await page.getByLabel('Ground Truth Field 02').fill('บริษัท ซีดีจี จำกัด\nABXD');
 await expect(page.getByTestId('global-evaluation')).toHaveCount(0);
 await page.getByRole('button',{name:'ยืนยันเพื่อคำนวณ',exact:true}).click();
 await expect(page).toHaveURL(/\/ground-truth(?:\?edit=1)?$/);
 const comparisonRow=page.getByTestId(`comparison-row-${fid}`);
 await expect(comparisonRow.getByTestId('global-metrics-mint').getByTestId('global-evaluation')).toBeVisible();
 await comparisonRow.getByTestId('global-result-mint').getByTestId('highlight-error').first().click();
 await expect(page.locator('[popover]:popover-open')).toContainText('อ่านผิด');await page.keyboard.press('Escape');
 for(const id of ids)await expect(comparisonRow.getByTestId(`global-metrics-${id}`)).toContainText('CER');
 await page.reload();await expect(page.getByTestId('global-field-nav')).toHaveCount(0);
 await expect(page.getByLabel('Ground Truth Field 02')).toHaveValue('บริษัท ซีดีจี จำกัด\nABXD');
 await page.goto(`/workflow/${c.id}/ground-truth`);
 await expect(comparisonRow.getByTestId('confirmed-global-gt')).toContainText('ABXD');
 const reopened=await(await request.get(`${api}/api/test-cases/${c.id}`)).json();expect(reopened.global_fields.map((f:{id:string})=>f.id)).toEqual(c.global_fields!.map(f=>f.id));
 await page.screenshot({path:'test-results/global-results.png',fullPage:true});
 await page.goto(`/history?document=${doc.id}`);await page.locator(`a[href="/test/${c.id}"]`).first().click();await expect(page).toHaveURL(new RegExp(`/workflow/${c.id}/ground-truth$`));
 await page.goto('/dataset');const rows=page.locator('tbody tr').filter({has:page.locator(`a[href="/test/${c.id}"]`)});await expect(rows).toHaveCount(4);const row=rows.filter({hasText:'Field 02'});await expect(row).toContainText('ABXD');
 await row.getByRole('checkbox').check();const pending=page.waitForResponse(r=>r.url().endsWith('/dataset/export'));const download=page.waitForEvent('download');await page.getByRole('button',{name:'ส่งออก ZIP (1 ที่พร้อม)',exact:true}).click();
 const response=await pending;expect(response.request().postDataJSON()).toEqual({test_case_ids:[],global_field_ids:[fid]});expect(await(await download).failure()).toBeNull();
});

test('calculation requires complete synchronized GT and persists both views without OCR',async({page,request})=>{
 const doc=await upload(page);await detect(page);const c=await confirm(page);await run(page);
 const root=`${api}/api/test-cases/${c.id}`;
 const calculate=async()=>{const response=page.waitForResponse(r=>r.url().endsWith('/evaluate'));await page.getByRole('button',{name:'ยืนยันเพื่อคำนวณ',exact:true}).click();expect((await response).status()).toBe(200);await expect(page).toHaveURL(/\/ground-truth(?:\?edit=1)?$/);};
 // Draft assistance never bypasses the explicit confirmation request.
 await page.getByLabel('Ground Truth Field 01').fill('');
 await expect(page.getByRole('button',{name:'ยืนยันเพื่อคำนวณ',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'Whole Field',exact:true}).click();
 const whole=page.getByLabel('Ground Truth ทั้งเอกสาร',{exact:true});
 for(const n of [1,2]){const reset=page.getByRole('button',{name:`คืนค่า Field 0${n} เป็น 1 บรรทัด`,exact:true});if(await reset.count())await reset.click();}
 await whole.fill('บริษัท ซีดีจี จำกัด\nบริษัท ซีดีจี จำกัด\nบริษัท ซีดีจี จำกัด');
 await page.getByRole('button',{name:'Sub-fields',exact:true}).click();
 for(const n of [1,2,3])await expect(page.getByLabel(`Ground Truth Field 0${n}`)).toHaveValue('บริษัท ซีดีจี จำกัด');
 let ocrCalls=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/jobs'))ocrCalls++;});
 await calculate();
 let saved=await(await request.get(root)).json();
 expect(saved.runs.every((r:PipelineRun)=>r.document_evaluation&&r.fields!.every(f=>f.evaluation))).toBeTruthy();
 expect((await(await request.get(`${api}/api/dataset/samples?document=${doc.id}`)).json()).total).toBe(3);
 // Editing a field invalidates its prior evaluation; confirmation replaces it.
 await page.getByRole('button',{name:'กลับไปแก้ Ground Truth',exact:true}).click();
 await page.getByLabel('Ground Truth Field 02').fill('บริษัท ซีดีจี จำกัด\nABXD');
 await page.getByRole('button',{name:'Whole Field',exact:true}).click();await expect(whole).toHaveValue(/ABXD/);
 await page.getByRole('button',{name:'Sub-fields',exact:true}).click();
 let calculations=0;page.on('request',r=>{if(r.url().endsWith('/evaluate'))calculations++;});await calculate();expect(calculations).toBe(1);
 const metrics=page.getByTestId(`comparison-row-${c.global_fields![1].id}`).getByTestId('global-metrics-mint');
 await expect(metrics.getByTestId('global-evaluation')).toBeVisible();
 await metrics.getByRole('button',{name:'ดูสถิติอักขระ',exact:true}).click();
 await expect(metrics.getByTestId('field-error-ground-truth')).toContainText('ABXD');
 await expect(metrics.getByTestId('field-error-raw-ocr')).toContainText('ABCD');
 await page.getByRole('button',{name:'Whole Field',exact:true}).click();
 await expect(page.getByTestId('global-metrics-mint').getByTestId('global-evaluation')).toBeVisible();
 saved=await(await request.get(root)).json();expect(saved.runs.every((r:PipelineRun)=>r.document_evaluation&&r.fields![1].evaluation)).toBeTruthy();
 expect(ocrCalls).toBe(0);expect(calculations).toBe(1);
 await page.reload();await expect(page.getByTestId('document-viewer')).toBeVisible();
 await page.getByRole('button',{name:'Sub-fields',exact:true}).click();await expect(page.getByLabel('Ground Truth Field 02')).toHaveValue('บริษัท ซีดีจี จำกัด\nABXD');
 await expect(page.getByRole('link',{name:/5\. Evaluation/})).toHaveCount(0);
});

test('global boxes move/resize/delete/add without losing other identities or zoom coordinates',async({page})=>{
 await upload(page);await draw(page,[100,200],[700,400]);
 const pending=page.waitForResponse(r=>r.url().endsWith('/global-fields')&&r.request().method()==='PUT');await page.getByRole('button',{name:'บันทึก Layout ฉบับร่าง',exact:true}).click();const firstSaved=await(await pending).json();const firstROI=firstSaved.global_fields[0].roi;
 for(const [key,target] of Object.entries({x1:100,y1:200,x2:700,y2:400}))expect(Math.abs(firstROI[key as keyof typeof firstROI]-target)).toBeLessThanOrEqual(3);
 await draw(page,[100,600],[700,800]);await expect(page.getByTestId('global-field-nav')).toHaveCount(2);
 const viewer=page.getByTestId('document-viewer'),canvas=viewer.locator('.konvajs-content');await viewer.getByRole('button',{name:'แก้ไขพื้นที่',exact:true}).click();await page.getByRole('button',{name:'Field 02',exact:true}).click();await canvas.scrollIntoViewIfNeeded();
 const point=async(x:number,y:number)=>{await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));const b=(await canvas.boundingBox())!,s=Number(await viewer.getAttribute('data-view-scale'));return {x:b.x+Number(await viewer.getAttribute('data-view-x'))+x*s,y:b.y+Number(await viewer.getAttribute('data-view-y'))+y*s};};
 const coords=async()=>(await viewer.getByText(/^พื้นที่ที่เลือก \(ROI\) \(/).textContent())!.match(/\d+/g)!.slice(0,4).map(Number);
 const before=await coords(),cx=(before[0]+before[2])/2,cy=(before[1]+before[3])/2,start=await point(cx,cy),end=await point(cx+50,cy+50);await page.mouse.move(start.x,start.y);await page.mouse.down();await page.mouse.move(end.x,end.y,{steps:10});await page.mouse.up();const moved=await coords();
 // Each browser pointer endpoint is quantized to a CSS pixel at the current zoom.
 const tolerance=Math.ceil(2/Number(await viewer.getAttribute('data-view-scale')));
 expect(Math.abs(moved[0]-before[0]-50)).toBeLessThanOrEqual(tolerance);expect(Math.abs(moved[1]-before[1]-50)).toBeLessThanOrEqual(tolerance);
 expect(moved[2]-moved[0]).toBe(before[2]-before[0]);expect(moved[3]-moved[1]).toBe(before[3]-before[1]);
 const corner=await point(moved[2],moved[3]),larger=await point(moved[2]+40,moved[3]+30);await page.mouse.move(corner.x,corner.y);await page.mouse.down();await page.mouse.move(larger.x,larger.y,{steps:10});await page.mouse.up();const resized=await coords();expect(resized[2]-resized[0]).toBeGreaterThan(moved[2]-moved[0]);expect(resized[3]-resized[1]).toBeGreaterThan(moved[3]-moved[1]);
 await expect(page.getByTestId('global-field-nav')).toHaveCount(2);await page.getByRole('button',{name:'ลบ Field 02',exact:true}).click();await expect(page.getByTestId('global-field-nav')).toHaveCount(1);await draw(page,[80,800],[800,1000]);const c=await confirm(page);expect(c.global_fields).toHaveLength(2);expect(c.global_fields![0].roi).toEqual(firstROI);
});

test('four-page PDF navigation preserves saved layout per selected page',async({page})=>{
 const doc=await upload(page,true);await detect(page);const first=await confirm(page);
 await page.getByRole('link',{name:/1\. Upload/}).click();await page.getByLabel('เลือกหน้า PDF').selectOption('2');
 await page.getByRole('button',{name:'ถัดไป: จัดการ Layout',exact:true}).click();await expect(page.getByTestId('global-field-nav')).toHaveCount(0);
 await detect(page);const second=await confirm(page);expect(second.id).not.toBe(first.id);expect(second.document.id).toBe(doc.id);expect(second.page_number).toBe(2);await run(page);
 await page.goto(`/workflow/${first.id}/pipelines`);await expect(page.getByTestId('global-field-nav')).toHaveCount(0);await expect(page.getByRole('button',{name:'Run OCR',exact:true})).toBeEnabled();
});

test('image upload refresh, bulk layout selection and safe back navigation preserve historical runs',async({page,request})=>{
 const doc=await upload(page);await detect(page);

 await page.getByRole('button',{name:'ลบ Field 03',exact:true}).click();await page.getByRole('button',{name:'ลบ Field 01',exact:true}).click();
 await expect(page.getByTestId('global-field-nav')).toHaveCount(1);
 const c=await confirm(page);await page.reload();await expect(page.getByTestId('global-field-nav')).toHaveCount(0);
 await page.getByRole('link',{name:/1\. Upload/}).click();await expect(page.getByAltText('เอกสารที่อัปโหลด')).toBeVisible();
 await page.reload();await expect(page.getByAltText('เอกสารที่อัปโหลด')).toBeVisible();await expect(page.getByTestId('workflow-upload').getByRole('alert')).toHaveCount(0);await expect(page).toHaveURL(new RegExp(`document=${doc.id}$`));
 await page.goto(`/workflow/${c.id}/layout`);
 await expect(page.getByRole('button',{name:'เพิ่มกรอบ Manual',exact:true})).toBeVisible();await confirm(page);
 // A subset selection must really produce a single run, rather than always all configured pipelines.
 await expect(page.getByRole('checkbox',{name:'เลือก Mint Pipeline',exact:true})).toBeVisible();
 for(const box of await page.getByTestId('pipeline-options').getByRole('checkbox').all())await box.uncheck();await page.getByRole('checkbox',{name:'เลือก Mint Pipeline',exact:true}).check();
 await page.getByRole('button',{name:'Run OCR',exact:true}).click();await expect(page).toHaveURL(/\/ground-truth(?:\?edit=1)?$/);
 const historical=await(await request.get(`${api}/api/test-cases/${c.id}`)).json();expect(historical.runs.map((r:PipelineRun)=>r.pipeline_id)).toEqual(['mint']);
 await page.getByRole('link',{name:/2\. Global Layout/}).click();await draw(page,[80,800],[800,1000]);const revision=await confirm(page);expect(revision.id).not.toBe(c.id);
 const preserved=await(await request.get(`${api}/api/test-cases/${c.id}`)).json();expect(preserved.global_fields).toEqual(historical.global_fields);expect(preserved.runs).toEqual(historical.runs);
});

for(const width of [390,768,1440])test(`global workflow responsive ${width}`,async({page})=>{
 await page.setViewportSize({width,height:1000});await upload(page);await detect(page);await confirm(page);await run(page);
 await page.getByLabel('Ground Truth Field 01').fill('บริษัท ซีดีจี จำกัด\nABXD');await page.getByRole('button',{name:'ยืนยันเพื่อคำนวณ',exact:true}).click();await expect(page).toHaveURL(/\/ground-truth(?:\?edit=1)?$/);await expect(page.getByTestId('global-result-mint').first()).toBeVisible();
 await expect(page.getByTestId('global-metrics-mint').first().getByTestId('global-evaluation')).toBeVisible();await expect(page.getByTestId('document-viewer')).toHaveCount(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);await page.screenshot({path:`test-results/global-${width}.png`,fullPage:true});
});
