import {test,expect} from "@playwright/test";
import path from "node:path";
import {randomUUID} from "node:crypto";
const api=process.env.E2E_API_URL||"http://127.0.0.1:8100";

for(const width of [390,768,1440])test(`document types, one-pipeline History, dataset exclusion and log search ${width}`,async({page,request})=>{
 await page.setViewportSize({width,height:1000});await page.goto('/');
 await page.getByLabel('ประเภทเอกสาร',{exact:true}).selectOption({label:'บัตรประชาชนไทย'});
 await page.getByRole('button',{name:'เพิ่มประเภทเอกสาร',exact:true}).click();
 const name=`ใบเสร็จ ${randomUUID().slice(0,8)}`;
 await page.getByLabel('ชื่อประเภทเอกสาร',{exact:true}).fill(name);await page.getByRole('button',{name:'เพิ่มประเภท',exact:true}).click();
 await expect(page.getByRole('dialog')).not.toBeVisible();await expect(page.getByLabel('ประเภทเอกสาร',{exact:true}).locator('option:checked')).toHaveText(name);
 const pending=page.waitForResponse(r=>r.url().endsWith('/api/documents')&&r.request().method()==='POST');
 await page.locator('input[type=file]').setInputFiles(path.resolve('public/sample-document.png'));const doc=await(await pending).json();expect(doc.document_type_name).toBe(name);
 await page.getByRole('button',{name:'ถัดไป: จัดการ Layout',exact:true}).click();await expect(page).toHaveURL(/\/layout$/);const id=page.url().split('/').at(-2)!;
 const fieldId=randomUUID();expect((await request.put(`${api}/api/test-cases/${id}/global-fields`,{data:{fields:[{id:fieldId,field_index:1,source:'manual',roi:{x1:80,y1:225,x2:850,y2:355}}],confirmed:false}})).ok()).toBeTruthy();
 await page.reload();await expect(page.locator('main')).toContainText(name);await page.getByRole('button',{name:'ยืนยัน ROI',exact:true}).click();await expect(page).toHaveURL(/\/pipelines$/);await expect(page.locator('main')).toContainText(name);
 await expect(page.getByTestId('pipeline-options').locator('input:checked')).toHaveCount(3);
 await expect(page.getByRole('button',{name:'Run OCR',exact:true})).toBeEnabled();
 for(const box of await page.getByTestId('pipeline-options').getByRole('checkbox').all())await box.uncheck();await page.getByRole('checkbox',{name:'เลือก Hutch fine tune v2',exact:true}).check();
 await page.getByRole('button',{name:'Run OCR',exact:true}).click();await expect(page).toHaveURL(/\/ground-truth\?edit=1$/);await expect(page.locator('main')).toContainText(name);
 await page.getByLabel('Ground Truth Field 01',{exact:true}).fill('ยืนยัน ใบเสร็จ');await page.getByRole('button',{name:'ยืนยันเพื่อคำนวณ',exact:true}).click();await expect(page.getByTestId('global-metrics-hutch_fine_tune_v2').getByTestId('global-evaluation')).toBeVisible();
 const before=await(await request.get(`${api}/api/test-cases/${id}`)).json();expect(before.history_status).toBe('success');
 await page.goto(`/history?document=${doc.id}`);const history=page.getByRole('row').filter({has:page.locator(`a[href="/test/${id}"]`)});await expect(history).toContainText('สำเร็จ');await expect(history).toContainText(name);
 await page.goto('/dataset');await expect(page.locator('tbody tr').first()).toContainText(name);const row=page.locator('tbody tr').filter({hasText:name});await row.getByRole('button',{name:'นำออกจาก Dataset',exact:true}).click();await page.getByRole('button',{name:'ยืนยันนำออก',exact:true}).click();await expect(row).toHaveCount(0);
 const after=await(await request.get(`${api}/api/test-cases/${id}`)).json();expect(after.runs).toEqual(before.runs);expect(after.global_fields).toEqual(before.global_fields);
 let excludedExport=await request.post(`${api}/api/dataset/export`,{data:{global_field_ids:[fieldId]}});
 if(excludedExport.status()===429){
  // Concurrent preview/crop reads may own the bounded image slot. Respect one
  // overload response, then still require the original exclusion validation.
  const delay=Number(excludedExport.headers()['retry-after']);expect(delay).toBeGreaterThan(0);expect(delay).toBeLessThanOrEqual(5);
  await new Promise(resolve=>setTimeout(resolve,delay*1000));
  excludedExport=await request.post(`${api}/api/dataset/export`,{data:{global_field_ids:[fieldId]}});
 }
 expect(excludedExport.status()).toBe(422);
 await page.goto('/logs');await expect(page.getByText('ไม่ได้เปิดการบันทึก System Logs ลงฐานข้อมูล',{exact:true})).toBeVisible();await expect(page.locator('tbody tr')).toHaveCount(0);
 await page.goto('/');await page.getByRole('button',{name:'จัดการประเภท',exact:true}).click();await page.getByRole('button',{name:`ลบ ${name}`,exact:true}).click();await page.getByRole('button',{name:'ยืนยันลบประเภท',exact:true}).click();await expect(page.getByRole('button',{name:`ลบ ${name}`,exact:true})).toHaveCount(0);await page.getByRole('button',{name:'ปิด',exact:true}).click();
 await expect(page.getByLabel('ประเภทเอกสาร',{exact:true}).getByRole('option',{name,exact:true})).toHaveCount(0);
 expect((await(await request.get(`${api}/api/test-cases/${id}`)).json()).document.document_type_name).toBe(name);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
});
