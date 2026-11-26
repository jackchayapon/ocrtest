import {test,expect} from '@playwright/test';
import {mockUX} from './ux-stability-fixture';

test('clicking a GT box scrolls only the field list and preserves page and image view',async({page})=>{
 const state=await mockUX(page,1,{groundTruth:true}),record=state.record;
 record.global_fields[0].roi={x1:0,y1:0,x2:600,y2:400};
 const refs=Array.from({length:25},(_,i)=>({id:`gt-${i}`,text:`Line ${i+1}`,roi:{x1:100,y1:20+i*13,x2:450,y2:28+i*13}}));
 record.ground_truth_raw=refs.map(r=>r.text).join('\n');record.global_fields[0].ground_truth_raw=record.ground_truth_raw;
 for(const run of record.runs)run.final_text=record.ground_truth_raw;
 await page.route('**/api/test-cases/ux-case/full-image-alignment',route=>route.fulfill({json:{references:refs,geometry_available:true}}));
 await page.goto('/workflow/ux-case/ground-truth?edit=1');
 await page.getByRole('button',{name:'Sub-fields',exact:true}).click();
 const viewer=page.getByTestId('document-viewer');await expect(viewer).toHaveAttribute('aria-busy','false');
 await viewer.evaluate(el=>window.scrollTo(0,window.scrollY+el.getBoundingClientRect().top-16));
 const before=await viewer.evaluate(el=>({scroll:window.scrollY,x:Number(el.getAttribute('data-view-x')),y:Number(el.getAttribute('data-view-y')),scale:Number(el.getAttribute('data-view-scale'))}));
 const canvas=(await viewer.locator('.konvajs-content').boundingBox())!;
 const fixedCanvas=viewer.locator('.konvajs-content canvas').nth(1);
 await fixedCanvas.evaluate(element=>{
  const canvas=element as HTMLCanvasElement,context=canvas.getContext('2d')!;
  const clear=context.clearRect.bind(context);
  canvas.dataset.clears='0';
  context.clearRect=(...args:Parameters<CanvasRenderingContext2D['clearRect']>)=>{canvas.dataset.clears=String(Number(canvas.dataset.clears)+1);clear(...args);};
 });
 await page.mouse.click(canvas.x+before.x+300*before.scale,canvas.y+before.y+336*before.scale);
 await expect(viewer).toHaveAttribute('data-active-field','gt-24');
 const list=page.getByRole('region',{name:'ช่องกรอก Ground Truth ตาม Field'});
 await expect.poll(()=>list.evaluate(el=>el.scrollTop)).toBeGreaterThan(100);
 expect(await page.evaluate(()=>window.scrollY)).toBe(before.scroll);
 await expect(viewer).toHaveAttribute('data-view-scale',String(before.scale));
 await expect(viewer).toHaveAttribute('data-view-x',String(before.x));
 await expect(viewer).toHaveAttribute('data-view-y',String(before.y));
 await expect(fixedCanvas).toHaveAttribute('data-clears','0');
});

test('reopening restores saved identities regardless of JSON coordinate key order and GT subfields select their boxes',async({page})=>{
 const state=await mockUX(page,1,{groundTruth:true}),record=state.record;
 record.global_fields[0].roi={x1:0,y1:0,x2:600,y2:400};record.ground_truth_raw='A\nB';record.global_fields[0].ground_truth_raw='A\nB';
 const run=record.runs[0],fid=run.fields[0].id;
 run.final_text='B\nA';run.fields[0].diagnostics={boxes:[{bbox:[10,100,150,125],text:'B'},{bbox:[10,20,150,45],text:'A'}]};
 const refs=[{id:'gt-0',text:'A',roi:{x1:10,y1:20,x2:150,y2:45}},{id:'gt-1',text:'B',roi:{x1:10,y1:100,x2:150,y2:125}}];
 const overrides=[{box_id:`${fid}:0`,reference_id:'gt-1'},{box_id:`${fid}:1`,reference_id:'gt-0'}];
 Object.assign(record,{full_image_alignment:{[run.id]:{fixed_gt:true,padding_version:1,source_ground_truth:'A\nB',ground_truth_raw:'A\nB',prediction:'A\nB',confirmed_at:'2026-11-25T00:00:00Z',overrides,references:refs.map(r=>({...r,roi:{x1:r.roi.x1,x2:r.roi.x2,y1:r.roi.y1,y2:r.roi.y2}}))}}});
 await page.route('**/api/test-cases/ux-case/full-image-alignment',route=>route.fulfill({json:{references:refs,geometry_available:true}}));
 await page.route('**/api/test-cases/ux-case/spatial-comparison',async route=>{
  expect(route.request().postDataJSON().overrides).toEqual(overrides);
  await route.fulfill({json:{run_id:run.id,geometry_available:true,missing:0,extra:0,ambiguous:0,inversions:[],rows:refs.map((r,i)=>({id:r.id,order:i+1,status:'matched'})),matches:overrides.map(o=>({id:o.box_id,reference_id:o.reference_id,candidates:[{reference_id:o.reference_id,overlap:1}]}))}});
 });
 await page.goto('/workflow/ux-case/ground-truth?edit=1');
 const form=page.getByTestId('full-image-line-fields');
 await expect(form.getByRole('heading',{name:'ตรวจสอบกรอบ DET ของแต่ละ Pipeline'})).toBeVisible();
 await form.getByRole('button',{name:'Sub-fields',exact:true}).click();
 const gtViewer=page.getByTestId('document-viewer');
 await expect(gtViewer).toHaveAttribute('aria-busy','false');
 const initialView=await gtViewer.evaluate(el=>['data-view-x','data-view-y','data-view-scale'].map(key=>el.getAttribute(key)));
 await form.getByLabel('Ground Truth Field 02',{exact:true}).focus();
 await expect(page.getByTestId('document-viewer')).toHaveAttribute('data-active-field','gt-1');
 expect(await gtViewer.evaluate(el=>['data-view-x','data-view-y','data-view-scale'].map(key=>el.getAttribute(key)))).toEqual(initialView);
 await expect(form).toContainText('ตำแหน่ง (10, 100) – (150, 125)');
 for(let attempt=0;attempt<2;attempt++){
  await form.getByRole('button',{name:'ตรวจและจัดตำแหน่ง GT เทียบ DET แต่ละ Pipeline'}).click();
  const dialog=page.getByRole('dialog');
  await expect(dialog.getByLabel('Pipeline Field แรก').locator(`option[value="${fid}:0"]`)).toHaveText('Field 02 · กรอบ DET 1');
  await expect(dialog.getByText('สลับแล้ว',{exact:true})).toHaveCount(2);
  await dialog.getByRole('button',{name:'ปิดรายละเอียด',exact:true}).click();
 }
 expect(state.gtPuts).toBe(0);
});

test('check automatically compares fixed boxes and swaps only field identities',async({page})=>{
 const state=await mockUX(page,1,{groundTruth:true});
 const record=state.record;
 record.global_fields[0].roi={x1:0,y1:0,x2:600,y2:400};
 record.ground_truth_raw='A\nB\nmissing';record.global_fields[0].ground_truth_raw=record.ground_truth_raw;
 for(const run of record.runs){run.final_text='B\nA';run.fields[0].diagnostics={boxes:[{bbox:[10,50,100,70],text:'B'},{bbox:[10,10,100,30],text:'A'}]};}
 const confirmations:Record<string,unknown>[]=[];
 const inspections:Record<string,unknown>[]=[];
 const references=[{id:'gt-0',text:'A',roi:{x1:10,y1:10,x2:100,y2:30}},{id:'gt-1',text:'B',roi:{x1:10,y1:50,x2:100,y2:70}},{id:'gt-2',text:'missing',roi:null}];
 await page.route('**/api/test-cases/ux-case/global-ground-truth',async route=>{
  const data=route.request().postDataJSON();record.ground_truth_raw=data.ground_truth_raw;record.global_fields[0].ground_truth_raw=data.ground_truth_raw;
  await route.fulfill({json:record});
 });
 await page.route('**/api/test-cases/ux-case/spatial-comparison',async route=>{
  const data=route.request().postDataJSON();inspections.push(data);
  const fid=record.runs.find(r=>r.id===data.run_id)!.fields[0].id;
  const matches=[0,1].map(i=>({id:`${fid}:${i}`,order:i+1,reference_id:data.overrides.find((o:{box_id:string})=>o.box_id===`${fid}:${i}`)?.reference_id,candidates:[{reference_id:`gt-${1-i}`,overlap:1}]}));
  await route.fulfill({json:{run_id:data.run_id,geometry_available:true,gt_confirmed:false,order_complete:false,missing:1,extra:0,ambiguous:0,inversions:[],matches,rows:data.references.map((r:{id:string;text:string},i:number)=>({id:r.id,order:i+1,ground_truth:r.text,prediction:r.text,model_orders:i<2?[i+1]:[],status:i<2?'matched':'missing',metrics:null}))}});
 });
 await page.route('**/api/test-cases/ux-case/full-image-alignment',async route=>{
  if(route.request().method()==='GET')return route.fulfill({json:{references,geometry_available:true}});
  const data=route.request().postDataJSON();confirmations.push(data);
  Object.assign(record,{full_image_alignment:{[data.run_id]:{...data,fixed_gt:true,source_ground_truth:record.ground_truth_raw,ground_truth_raw:data.references.map((r:{text:string})=>r.text).join("\n"),confirmed_at:'2026-11-24T00:00:00Z'}}});
  await route.fulfill({json:record});
 });
 await page.goto('/workflow/ux-case/ground-truth?edit=1');
 await page.getByRole('button',{name:'ตรวจและจัดตำแหน่ง GT เทียบ DET แต่ละ Pipeline'}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog).toContainText('กรอบขาด 1');
 await expect(dialog).toContainText('กรอบตำแหน่งไม่ตรง 2');
 expect(inspections.length).toBeGreaterThan(0);
 expect(inspections[0].references).toEqual(references);
 await expect(dialog.getByRole('button',{name:/วาดกรอบ|ตั้งต้นกรอบ|เลื่อน GT/})).toHaveCount(0);
 await expect(dialog).toContainText('ไม่มีกรอบ — คง Field ไว้');
 const boxId=record.runs[0].fields[0].id;
 await dialog.getByLabel('Pipeline Field แรก',{exact:true}).selectOption(`${boxId}:0`);
 await dialog.getByLabel('สลับกับ Pipeline Field',{exact:true}).selectOption(`${boxId}:1`);
 await dialog.getByRole('button',{name:'สลับ Pipeline Field ID',exact:true}).click();
 await expect(dialog).toContainText('กรอบตำแหน่งไม่ตรง 0');
 await expect(dialog.getByLabel('Pipeline จัดตำแหน่ง')).toBeDisabled();
 await dialog.getByRole('button',{name:'ยืนยันเทียบข้อความเดิม (พิกัดไม่ครบ)'}).click();
 await expect(dialog).toContainText('บันทึก Field ID แล้ว');
 await expect(dialog).toContainText('กรอบตำแหน่งไม่ตรง 0');
 expect(confirmations).toHaveLength(1);
 expect((confirmations[0].references as {text:string;roi:unknown}[]).map(r=>r.text)).toEqual(['A','B','missing']);
 expect(confirmations[0].references).toEqual(references);
 expect(confirmations[0].overrides).toEqual([{box_id:`${boxId}:0`,reference_id:'gt-1'},{box_id:`${boxId}:1`,reference_id:'gt-0'}]);
 expect(inspections.every(data=>JSON.stringify(data.references)===JSON.stringify(references))).toBe(true);
 expect((confirmations[0].references as {roi:unknown}[])[2].roi).toBeNull();
 await dialog.getByRole('button',{name:'ปิดรายละเอียด',exact:true}).click();
 await page.getByRole('button',{name:'ตรวจและจัดตำแหน่ง GT เทียบ DET แต่ละ Pipeline'}).click();
 await expect(dialog).toContainText('บันทึก Field ID แล้ว');
 expect(state.jobPosts).toBe(0);
});

test('missing middle field is a locked empty placeholder and later IDs keep GT numbering',async({page})=>{
 const state=await mockUX(page,1,{groundTruth:true});
 const record=state.record;
 record.global_fields[0].roi={x1:0,y1:0,x2:600,y2:400};
 record.ground_truth_raw='A\nB\nC';record.global_fields[0].ground_truth_raw=record.ground_truth_raw;
 const refs=['A','B','C'].map((text,i)=>({id:`gt-${i}`,text,roi:{x1:10,y1:10+i*40,x2:100,y2:30+i*40}}));
 for(const r of record.runs){r.final_text='A\nC';r.fields[0].diagnostics={boxes:[{bbox:[10,10,100,30],text:'A'},{bbox:[10,90,100,110],text:'C'}]};}
 const confirmed:Record<string,unknown>[]=[];
 await page.route('**/api/test-cases/ux-case/full-image-alignment',async route=>{
  if(route.request().method()==='GET')return route.fulfill({json:{references:refs,geometry_available:true}});
  confirmed.push(route.request().postDataJSON());return route.fulfill({json:record});
 });
 await page.route('**/api/test-cases/ux-case/spatial-comparison',async route=>{
  const data=route.request().postDataJSON(),fid=record.runs[0].fields[0].id;
  expect(data.overrides).toEqual([]);
  await route.fulfill({json:{run_id:data.run_id,geometry_available:true,missing:1,extra:0,ambiguous:0,inversions:[],rows:refs.map((r,i)=>({id:r.id,order:i+1,status:i===1?'missing':'matched',prediction:i===1?'':r.text})),matches:[0,2].map((n,i)=>({id:`${fid}:${i}`,order:i+1,reference_id:`gt-${n}`,candidates:[{reference_id:`gt-${n}`,overlap:1}]}))}});
 });
 await page.goto('/workflow/ux-case/ground-truth?edit=1');
 await page.getByRole('button',{name:'ตรวจและจัดตำแหน่ง GT เทียบ DET แต่ละ Pipeline'}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog.getByTestId('placeholder-gt-1')).toContainText('Field 02 · Field ว่าง · ล็อก');
 await expect(dialog).toContainText('Pipeline พบจริง 2 กรอบ + Field ว่าง 1');
 await expect(dialog.getByLabel('Pipeline Field แรก').locator('option')).toHaveText(['เลือกกรอบ Pipeline','Field 01 · กรอบ DET 1','Field 03 · กรอบ DET 2']);
 await expect(dialog.getByTestId('placeholder-gt-1').getByRole('button')).toHaveCount(0);
 await dialog.getByRole('button',{name:'ยืนยัน Field ID สำหรับ Pipeline นี้'}).click();
 await expect.poll(()=>confirmed.length).toBe(1);
 expect(confirmed[0].references).toEqual(refs);
 expect(confirmed[0].overrides).toEqual([{box_id:`${record.runs[0].fields[0].id}:0`,reference_id:'gt-0'},{box_id:`${record.runs[0].fields[0].id}:1`,reference_id:'gt-2'}]);
 expect(state.jobPosts).toBe(0);
});

test('one toolbar synchronizes both views and combines background drag with field selection',async({page})=>{
 const state=await mockUX(page,1,{groundTruth:true}),record=state.record;
 record.global_fields[0].roi={x1:0,y1:0,x2:600,y2:400};
 record.ground_truth_raw='A';record.global_fields[0].ground_truth_raw='A';
 for(const r of record.runs){r.final_text='A';r.fields[0].diagnostics={boxes:[{bbox:[100,100,200,140],text:'A'}]};}
 const refs=[{id:'gt-0',text:'A',roi:{x1:100,y1:100,x2:200,y2:140}}];
 await page.route('**/api/test-cases/ux-case/full-image-alignment',route=>route.fulfill({json:{references:refs,geometry_available:true}}));
 await page.route('**/api/test-cases/ux-case/spatial-comparison',async route=>{
  const data=route.request().postDataJSON(),fid=record.runs[0].fields[0].id;
  await route.fulfill({json:{run_id:data.run_id,geometry_available:true,missing:0,extra:0,ambiguous:0,inversions:[],rows:[{id:'gt-0',order:1,status:'matched'}],matches:[{id:`${fid}:0`,order:1,reference_id:'gt-0',candidates:[{reference_id:'gt-0',overlap:1}]}]}});
 });
 await page.goto('/workflow/ux-case/ground-truth?edit=1');
 await page.getByRole('button',{name:'ตรวจและจัดตำแหน่ง GT เทียบ DET แต่ละ Pipeline'}).click();
 const dialog=page.getByRole('dialog'),views=dialog.getByTestId('document-viewer');
 await expect(dialog.getByRole('toolbar')).toHaveCount(1);
 await expect(views).toHaveCount(2);
 await expect(views.nth(0)).toHaveAttribute('aria-busy','false');
 await expect(views.nth(1)).toHaveAttribute('aria-busy','false');
 const transforms=()=>views.evaluateAll(elements=>elements.map(el=>({scale:Number(el.getAttribute('data-view-scale')),x:Number(el.getAttribute('data-view-x')),y:Number(el.getAttribute('data-view-y'))})));
 await dialog.getByRole('button',{name:'ซูมทั้งสองภาพ 100%',exact:true}).click();
 await expect.poll(async()=>(await transforms()).map(v=>v.scale)).toEqual([1,1]);
 for(let i=0;i<5;i++)await dialog.getByRole('button',{name:'ขยายทั้งสองภาพ',exact:true}).click();
 await expect.poll(async()=>{const v=await transforms();return v[0].scale===v[1].scale&&v[0].scale>3;}).toBe(true);
 const canvas=views.nth(1).locator('.konvajs-content');
 const bounds=(await canvas.boundingBox())!;
 const before=await transforms();
 await page.mouse.move(bounds.x+bounds.width/2,bounds.y+bounds.height/2);
 await page.mouse.down();await page.mouse.move(bounds.x+bounds.width/2+55,bounds.y+bounds.height/2+45,{steps:6});await page.mouse.up();
 await expect.poll(async()=>{const v=await transforms();return Math.abs(v[0].x-before[0].x-55)<2&&Math.abs(v[1].x-before[1].x-55)<2&&Math.abs(v[0].y-before[0].y-45)<2&&Math.abs(v[1].y-before[1].y-45)<2;}).toBe(true);
 await page.keyboard.down('Control');await page.mouse.wheel(0,-80);await page.keyboard.up('Control');
 await expect.poll(async()=>{const v=await transforms();return v[0].scale===v[1].scale&&v[0].scale>before[0].scale;}).toBe(true);
 await dialog.getByRole('button',{name:'พอดีหน้าจอทั้งสองภาพ',exact:true}).click();
 const fit=await transforms(),rect=(await canvas.boundingBox())!;
 await page.mouse.click(rect.x+fit[1].x+150*fit[1].scale,rect.y+fit[1].y+120*fit[1].scale);
 await expect(dialog.getByLabel('Pipeline Field แรก',{exact:true})).toHaveValue(`${record.runs[0].fields[0].id}:0`);
 expect(await transforms()).toEqual(fit);
 await dialog.getByRole('button',{name:'ซ่อนชื่อ Field ทั้งสองภาพ'}).click();
 await expect(views.nth(0)).toHaveAttribute('data-show-field-labels','false');
 await expect(views.nth(1)).toHaveAttribute('data-show-field-labels','false');
 expect(state.gtPuts).toBe(0);expect(state.jobPosts).toBe(0);
});
