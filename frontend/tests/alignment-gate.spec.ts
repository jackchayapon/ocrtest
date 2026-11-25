import {test,expect} from '@playwright/test';
import {mockUX} from './ux-stability-fixture';

for(const fullImage of [false,true])test(`calculation loading reports completed steps and elapsed time, full image=${fullImage}`,async({page})=>{
 const state=await mockUX(page,1,{groundTruth:true});
 if(fullImage)state.record.global_fields[0].roi={x1:0,y1:0,x2:600,y2:400};
 let release!:()=>void;
 const waiting=new Promise<void>(resolve=>{release=resolve;});
 await page.route('**/api/test-cases/ux-case/evaluate',async route=>{await waiting;await route.fulfill({json:state.record});});
 await page.goto('/workflow/ux-case/ground-truth?edit=1');
 await expect(page.getByRole('button',{name:'เลือกกรอบและเลื่อนเอกสาร',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'ยืนยันเพื่อคำนวณ',exact:true}).click();
 const loading=page.getByRole('dialog',{name:'กำลังเตรียมและคำนวณ CER/WER',exact:true});
 await expect(loading).toBeVisible();
 await expect(loading.getByTestId('loading-hand')).toBeVisible();
 await expect(loading.getByRole('progressbar')).toHaveAttribute('value',fullImage?'2':'1');
 await expect(loading.getByRole('progressbar')).toHaveAttribute('max',fullImage?'3':'2');
 await expect(loading).toContainText('เวลาที่ใช้ 0 นาที 1 วินาที');
 await page.keyboard.press('Escape');await expect(loading).toBeVisible();
 release();
 await expect(loading).toHaveCount(0);
 await expect(page.getByTestId('comparison-scroll')).toBeVisible();
});

test('evaluation screen no longer exposes the experimental DET mode',async({page})=>{
 const state=await mockUX(page,1,{groundTruth:true});
 state.record.global_fields[0].roi={x1:0,y1:0,x2:600,y2:400};
 await page.goto('/workflow/ux-case/ground-truth');
 await expect(page.getByTestId('comparison-scroll')).toBeVisible();
 await expect(page.getByRole('button',{name:'ตรวจตำแหน่งและลำดับ DET',exact:true})).toHaveCount(0);
});

test('matching pipelines proceed directly to calculation without a review dialog',async({page})=>{
 const state=await mockUX(page,1,{groundTruth:true});
 state.record.global_fields[0].roi={x1:0,y1:0,x2:600,y2:400};
 let evaluations=0;
 await page.route('**/api/test-cases/ux-case/evaluate',async route=>{evaluations++;expect(route.request().postDataJSON().require_spatial_review).toBe(true);await route.fulfill({json:state.record});});
 await page.goto('/workflow/ux-case/ground-truth?edit=1');
 await page.getByRole('button',{name:'ยืนยันเพื่อคำนวณ',exact:true}).click();
 await expect(page.getByTestId('comparison-scroll')).toBeVisible();
 await expect(page.getByRole('dialog')).toHaveCount(0);
 expect(evaluations).toBe(1);
});

test('calculate checks all pipelines and opens the red pipeline before evaluating',async({page})=>{
 const state=await mockUX(page,1,{groundTruth:true});
 const record=state.record;record.global_fields[0].roi={x1:0,y1:0,x2:600,y2:400};
 record.ground_truth_raw='A\nB';record.global_fields[0].ground_truth_raw='A\nB';
 const refs=['A','B'].map((text,i)=>({id:`gt-${i}`,text,roi:{x1:10,y1:10+i*40,x2:100,y2:30+i*40}}));
 for(const r of record.runs){r.final_text='A\nB';r.fields[0].diagnostics={boxes:[{bbox:[10,10,100,30],text:'A'},{bbox:[10,50,100,70],text:'B'}]};}
 let fixed=false,evaluations=0;
 await page.route('**/api/test-cases/ux-case/alignment-review',route=>route.fulfill({json:{ready:fixed,pipelines:record.runs.map((r,i)=>({run_id:r.id,pipeline_id:r.pipeline_id,ready:i!==1||fixed,reason:i!==1||fixed?'matched':'mismatch',mismatch:i===1&&!fixed?2:0,missing:0,extra:0,ambiguous:0}))}}));
 await page.route('**/api/test-cases/ux-case/full-image-alignment',async route=>{
  if(route.request().method()==='GET')return route.fulfill({json:{references:refs,geometry_available:true}});
  fixed=true;await route.fulfill({json:{...record,updated_at:'2026-11-25T00:00:00Z'}});
 });
 await page.route('**/api/test-cases/ux-case/spatial-comparison',async route=>{
  const data=route.request().postDataJSON(),r=record.runs.find(r=>r.id===data.run_id)!;
  const swapped=data.overrides[0]?.reference_id==='gt-1';
  await route.fulfill({json:{run_id:r.id,geometry_available:true,missing:0,extra:0,ambiguous:0,inversions:[],matches:[0,1].map(i=>({id:`${r.fields[0].id}:${i}`,reference_id:data.overrides[i]?.reference_id,candidates:[{reference_id:`gt-${1-i}`,overlap:1}]})),rows:refs.map((ref,i)=>({id:ref.id,order:i+1,status:'matched',model_orders:[swapped?2-i:i+1]}))}});
 });
 await page.route('**/api/test-cases/ux-case/evaluate',async route=>{evaluations++;expect(route.request().postDataJSON().require_spatial_review).toBe(true);await route.fulfill({json:record});});
 await page.goto('/workflow/ux-case/ground-truth?edit=1');
 await page.getByRole('button',{name:'ยืนยันเพื่อคำนวณ',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'จัดตำแหน่ง Ground Truth สำหรับรูปเต็ม',exact:true});await expect(dialog).toBeVisible();
 expect(evaluations).toBe(0);
 await expect(dialog.getByLabel('Pipeline จัดตำแหน่ง')).toHaveValue(record.runs[1].id);
 await expect(dialog.getByTestId(`alignment-status-${record.runs[0].id}`)).toContainText('✓');
 await expect(dialog.getByTestId(`alignment-status-${record.runs[1].id}`)).toContainText('✕');
 const fid=record.runs[1].fields[0].id;
 await dialog.getByLabel('Pipeline Field แรก').selectOption(`${fid}:0`);
 await dialog.getByLabel('สลับกับ Pipeline Field').selectOption(`${fid}:1`);
 await dialog.getByRole('button',{name:'สลับ Pipeline Field ID',exact:true}).click();
 await dialog.getByRole('button',{name:'ยืนยัน Field ID สำหรับ Pipeline นี้'}).click();
 await expect(dialog.getByTestId(`alignment-status-${record.runs[1].id}`)).toContainText('✓');
 const prompt=page.getByRole('dialog',{name:'ตรวจครบทุก Pipeline แล้ว',exact:true});
 await expect(prompt).toBeVisible();
 expect(evaluations).toBe(0);
 await prompt.getByRole('button',{name:'ตรวจครบแล้ว คำนวณ CER/WER'}).click();
 await expect(page.getByTestId('comparison-scroll')).toBeVisible();expect(evaluations).toBe(1);
});
