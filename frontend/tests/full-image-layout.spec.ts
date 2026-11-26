import {test,expect} from '@playwright/test';
import {mockUX} from './ux-stability-fixture';

test('full image hides drafts, restores them on switching, and submits only the full image on confirmation',async({page})=>{
 const state=await mockUX(page,2);
 const original=structuredClone(state.record.global_fields);
 const submissions:unknown[]=[];
 page.on('request',request=>{if(request.method()==='PUT'&&request.url().endsWith('/global-fields'))submissions.push(request.postDataJSON());});
 await page.goto('/workflow/ux-case/layout');
 await expect(page.getByTestId('global-field-nav')).toHaveCount(2);
 await page.getByRole('radio',{name:'ส่งรูปเต็ม',exact:true}).check();
 await expect(page.getByTestId('global-field-nav')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'เพิ่มกรอบ Manual',exact:true})).toHaveCount(0);
 expect(submissions).toHaveLength(0);
 await page.getByRole('radio',{name:'วาดกรอบ',exact:true}).check();
 await expect(page.getByTestId('global-field-nav')).toHaveCount(2);
 expect(state.record.global_fields).toEqual(original);
 await page.getByRole('radio',{name:'ส่งรูปเต็ม',exact:true}).check();
 await page.getByRole('button',{name:'ยืนยัน ROI',exact:true}).click();
 await expect(page).toHaveURL(/\/pipelines$/);
 expect(submissions).toHaveLength(1);
 expect(submissions[0]).toMatchObject({confirmed:true,fields:[{roi:{x1:0,y1:0,x2:600,y2:400},ground_truth_raw:null}]});
 expect(state.record.global_fields).toHaveLength(1);
 expect(original.some(f=>f.id===state.record.global_fields[0].id)).toBe(false);
});

test('full image can be confirmed without any drawn fields',async({page})=>{
 await mockUX(page,0);
 await page.goto('/workflow/ux-case/layout');
 await expect(page.getByRole('button',{name:'ยืนยัน ROI',exact:true})).toBeDisabled();
 await page.getByRole('radio',{name:'ส่งรูปเต็ม',exact:true}).check();
 await expect(page.getByRole('button',{name:'ยืนยัน ROI',exact:true})).toBeEnabled();
 await page.getByRole('button',{name:'ยืนยัน ROI',exact:true}).click();
 await expect(page).toHaveURL(/\/pipelines$/);
});
