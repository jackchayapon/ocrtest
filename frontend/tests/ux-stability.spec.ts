import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {mockUX} from './ux-stability-fixture';

test('authoritative config gates first Auto Layout, retry and duplicate clicks preserve manual ROIs',async({page})=>{
 let release!:()=>void;const gate=new Promise<void>(r=>{release=r;});
 const s=await mockUX(page,1,{configGate:gate,configFailures:1});
 await page.goto('/workflow/ux-case/layout');const auto=page.getByRole('button',{name:'Auto Layout',exact:true});
 await expect(auto).toBeDisabled();await expect(page.getByTestId('job-workload-limits')).not.toContainText('12 Fields');
 release();await expect(page.getByRole('button',{name:'ลองโหลดการตั้งค่าอีกครั้ง'})).toBeVisible();await expect(auto).toBeDisabled();
 await page.getByRole('button',{name:'ลองโหลดการตั้งค่าอีกครั้ง'}).click();await expect(auto).toBeEnabled();
 const original=structuredClone(s.record.global_fields[0]);
 await auto.evaluate(e=>{(e as HTMLButtonElement).click();(e as HTMLButtonElement).click();});
 await expect(page.getByTestId('global-field-nav')).toHaveCount(26);expect(s.autoCalls).toBe(1);
 await page.getByRole('button',{name:'บันทึก Layout ฉบับร่าง',exact:true}).click();await expect.poll(()=>s.record.global_fields.find(f=>f.id===original.id)).toMatchObject({id:original.id,roi:original.roi,source:original.source,ground_truth_raw:original.ground_truth_raw});
 s.autoRegions=81;await auto.click();await expect(page.getByTestId('workflow-layout').getByRole('alert')).toContainText('80 Fields');await expect(page.getByTestId('global-field-nav')).toHaveCount(26);
});

test('starting and polling a simulated Job preserves preview node, view, dimensions and scroll',async({page})=>{
 const s=await mockUX(page);await page.goto('/workflow/ux-case/pipelines');const viewer=page.getByTestId('document-viewer');await expect(viewer).toHaveAttribute('aria-busy','false');
 await viewer.getByRole('button',{name:'ซูมเข้า',exact:true}).click();
 const run=page.getByRole('button',{name:'Run OCR',exact:true});await expect(run).toBeEnabled();await run.scrollIntoViewIfNeeded();
 const node=await viewer.elementHandle(),before=await viewer.boundingBox(),view=await viewer.evaluate(e=>[e.getAttribute('data-view-scale'),e.getAttribute('data-view-x'),e.getAttribute('data-view-y'),window.scrollY]),images=s.imageCalls;
 await run.click();await expect(page.getByTestId('ocr-job-progress')).toBeVisible();await page.waitForTimeout(2800);
 expect(await viewer.evaluate((e,old)=>e===old,node)).toBe(true);expect(await viewer.boundingBox()).toEqual(before);
 expect(await viewer.evaluate(e=>[e.getAttribute('data-view-scale'),e.getAttribute('data-view-x'),e.getAttribute('data-view-y'),window.scrollY])).toEqual(view);
 expect(s.imageCalls).toBe(images);expect(s.jobPosts).toBe(1);
});

test('reload during OCR retries only transient preview GETs and restores same Job without a POST',async({page})=>{
 const s=await mockUX(page);s.jobExists=true;s.imageStatuses=[429,503,200];await page.goto('/workflow/ux-case/pipelines');
 await expect(page.getByTestId('document-viewer')).toHaveAttribute('aria-busy','false');expect(s.imageCalls).toBe(3);
 await page.reload();await expect(page.getByTestId('document-viewer')).toHaveAttribute('aria-busy','false');await expect(page.getByTestId('ocr-job-progress')).toContainText('กำลังประมวลผล OCR');expect(s.jobPosts).toBe(0);
 s.imageStatuses=[404];await page.reload();await expect(page.getByTestId('document-viewer').getByRole('alert')).toContainText('ไม่พบไฟล์ต้นฉบับ');const calls=s.imageCalls;await page.waitForTimeout(700);expect(s.imageCalls).toBe(calls);
 await page.getByRole('button',{name:'ลองใหม่',exact:true}).click();await expect(page.getByTestId('document-viewer')).toHaveAttribute('aria-busy','false');expect(s.jobPosts).toBe(0);
});

test('persistent transient image errors stop after five GET attempts and offer manual retry',async({page})=>{
 const s=await mockUX(page);s.jobExists=true;s.imageStatuses=[503,503,503,503,503];await page.goto('/workflow/ux-case/pipelines');
 await expect(page.getByTestId('document-viewer').getByRole('alert')).toContainText('ภาพยังไม่พร้อมใช้งาน');expect(s.imageCalls).toBe(5);
 await page.waitForTimeout(700);expect(s.imageCalls).toBe(5);expect(s.jobPosts).toBe(0);
 await page.getByRole('button',{name:'ลองใหม่',exact:true}).click();await expect(page.getByTestId('document-viewer')).toHaveAttribute('aria-busy','false');expect(s.imageCalls).toBe(6);
});

test('prefill remains an unfinished phase after 99 OCR units and only persisted results open GT',async({page})=>{
 const s=await mockUX(page,33);s.jobExists=true;s.phase='prefill';s.resultsReady=false;
 await page.goto('/workflow/ux-case/pipelines');await expect(page.getByTestId('ocr-job-progress')).toContainText('อ่าน OCR ครบแล้ว 99/99 รายการ');
 await expect(page.getByTestId('ocr-job-progress')).toContainText('Ground Truth — งานทั้งหมดยังไม่เสร็จ');await expect(page.getByTestId('ocr-job-progress')).toContainText('Field 4/33');
 await expect(page.getByTestId('ocr-job-progress')).not.toContainText('100%');await page.reload();await expect(page.getByTestId('ocr-job-progress')).toContainText('Field 4/33');expect(s.resultReads).toBe(0);
 s.phase='completed';await expect.poll(()=>s.resultReads).toBeGreaterThan(0);await expect(page).toHaveURL(/pipelines$/);await expect(page.getByTestId('ocr-job-progress')).toContainText('กำลังเปิดผลลัพธ์');
 s.resultsReady=true;await expect(page).toHaveURL(/ground-truth\?edit=1$/,{timeout:15000});await expect(page.getByTestId('gt-prefill-notice')).toContainText('บาง Field');expect(s.jobPosts).toBe(0);
});

test('text-preview navigation centers and focuses Fields 1/10/33/80 repeatedly without losing GT or scrolling the page',async({page})=>{
 const s=await mockUX(page,80,{groundTruth:true});await page.goto('/workflow/ux-case/ground-truth?edit=1');
 for(const n of [80,1,10,33,33]){
  const button=page.getByRole('button',{name:`ดูกรอบ Field ${String(n).padStart(2,'0')}`,exact:true});await button.scrollIntoViewIfNeeded();const y=await page.evaluate(()=>scrollY);
  await button.focus();await page.keyboard.press('Enter');const input=page.getByLabel(`Ground Truth Field ${String(n).padStart(2,'0')}`,{exact:true});await expect(input).toBeFocused();expect(await page.evaluate(()=>scrollY)).toBe(y);await expect(page.getByTestId('document-viewer')).toHaveAttribute('data-active-field','f'+n);
  await input.fill('typed '+n);await expect(input).toHaveValue('typed '+n);
 }
 await expect(page.getByLabel('Ground Truth Field 80',{exact:true})).toHaveValue('typed 80');expect(s.jobPosts).toBe(0);
});

for(const width of [1440,390])test(`lazy large stats/crop overlays preserve Thai evidence, page/ROI and focus at ${width}`,async({page})=>{
 await page.setViewportSize({width,height:1000});const s=await mockUX(page,80,{groundTruth:true,pdf:true});await page.goto('/workflow/ux-case/ground-truth');
 expect(s.insights).toHaveLength(0);await expect(page.getByRole('dialog')).toHaveCount(0);
 const cell=page.getByTestId('comparison-row-f33').getByTestId('global-metrics-p2'),opener=cell.getByRole('button',{name:'ดูสถิติอักขระ',exact:true});await opener.click();
 const dialog=page.getByRole('dialog');await expect(dialog).toContainText('Pipeline p2 · Field 33');await expect(dialog.getByRole('button',{name:/ไม้โท: 1/})).toBeVisible();expect(s.insights).toHaveLength(1);
 expect(new URL(s.insights[0]).searchParams.get('field_id')).toBe('f33');await expect(dialog).toContainText('ก้😀');await expect(dialog).toContainText('ก😀');expect(await page.evaluate(()=>document.body.style.overflow)).toBe('hidden');
 await dialog.getByRole('button',{name:/ดูภาพต้นฉบับ \(Field Crop\)/}).click();await expect(dialog).toHaveCount(1);await expect(dialog.getByAltText('ภาพต้นฉบับของ Field')).toBeVisible();
 const crop=new URL(s.crops.at(-1)!);expect(crop.searchParams.get('page_number')).toBe('2');expect(crop.searchParams.get('x1')).toBe(String(s.record.global_fields[32].roi.x1));
 await dialog.getByRole('button',{name:'100%',exact:true}).click();await expect(dialog.getByLabel('ระดับการซูม')).toHaveText('100%');await dialog.getByRole('button',{name:'ขยาย',exact:true}).click();await expect(dialog.getByLabel('ระดับการซูม')).toHaveText('125%');
 await dialog.getByRole('button',{name:'ดูเอกสารต้นฉบับ',exact:true}).click();await expect(dialog.getByAltText('เอกสารต้นฉบับ')).toBeVisible();expect(s.crops.some(u=>u.includes('/pages/2/image'))).toBe(true);
 expect((await dialog.boundingBox())!.width).toBeGreaterThan(width*.93);expect(await dialog.evaluate(e=>e.scrollWidth-e.clientWidth)).toBeLessThanOrEqual(2);
 await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(opener).toBeFocused();expect(await page.evaluate(()=>document.body.style.overflow)).not.toBe('hidden');
 const cropButton=cell.getByRole('button',{name:'ดูภาพต้นฉบับ (Field Crop)',exact:true});await cropButton.click();await expect(dialog.getByAltText('ภาพต้นฉบับของ Field')).toBeVisible();await page.keyboard.press('Escape');await expect(cropButton).toBeFocused();expect(s.jobPosts).toBe(0);
});

test('upload contention honors Retry-After, prevents duplicate clicks and creates one document',async({page})=>{
 const s=await mockUX(page);s.uploadMode='once';await page.goto('/');await expect(page.locator('input[type=file]')).toBeEnabled();
 await page.locator('input[type=file]').setInputFiles({name:'synthetic.png',mimeType:'image/png',buffer:readFileSync('public/sample-document.png')});
 await expect(page.getByTestId('workflow-upload').getByRole('status').filter({hasText:'กำลังรอคิวประมวลผลภาพ'})).toBeVisible();await expect(page.locator('input[type=file]')).toBeDisabled();
 await expect(page.getByAltText('เอกสารที่อัปโหลด')).toBeVisible();expect(s.uploadAttempts).toBe(2);expect(s.acceptedUploads).toBe(1);
});

for(const mode of ['ambiguous','unsafe','safe'])test(`upload ${mode}: no unsafe retry and waiting can be cancelled`,async({page})=>{
 const s=await mockUX(page);s.uploadMode=mode;await page.goto('/');await expect(page.locator('input[type=file]')).toBeEnabled();
 await page.locator('input[type=file]').setInputFiles({name:'synthetic.png',mimeType:'image/png',buffer:readFileSync('public/sample-document.png')});
 const alert=page.getByTestId('workflow-upload').getByRole('alert');
 if(mode==='safe'){await page.getByRole('button',{name:'ยกเลิกการรอ'}).click();await expect(alert).toContainText('ยกเลิก');}else await expect(alert).toBeVisible();
 await page.waitForTimeout(1200);expect(s.uploadAttempts).toBe(1);expect(s.acceptedUploads).toBe(mode==='ambiguous'?1:0);
});

test('an upload with an unknown acceptance outcome times out without automatic resubmission',async({page})=>{
 await page.clock.install();const s=await mockUX(page);let release!:()=>void;const gate=new Promise<void>(r=>{release=r;});
 await page.route('**/api/documents',async route=>{if(route.request().method()!=='POST')return route.fallback();s.uploadAttempts++;s.acceptedUploads++;await gate;await route.abort('failed').catch(()=>{});});
 await page.goto('/');await expect(page.locator('input[type=file]')).toBeEnabled();
 await page.locator('input[type=file]').setInputFiles({name:'synthetic.png',mimeType:'image/png',buffer:readFileSync('public/sample-document.png')});
 await expect.poll(()=>s.uploadAttempts).toBe(1);await page.clock.fastForward(31000);
 await expect(page.getByTestId('workflow-upload').getByRole('alert')).toContainText('อาจมีเอกสารบันทึกแล้ว');release();
 expect(s.uploadAttempts).toBe(1);expect(s.acceptedUploads).toBe(1);
});
