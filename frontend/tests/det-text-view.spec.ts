import {test,expect} from '@playwright/test';
import {mockUX} from './ux-stability-fixture';

test('preview separates same-row DET text without rewriting OCR or scores',async({page})=>{
 const state=await mockUX(page,1,{groundTruth:true});
 const run=state.record.runs[0];
 run.final_text='left right\ndate month';
 run.fields[0].ocr_text=run.final_text;
 run.fields[0].diagnostics={boxes:[
  {bbox:[10,10,100,30],text:'left'},{bbox:[300,10,500,30],text:'right'},
  {bbox:[10,60,100,80],text:'date'},{bbox:[300,60,500,80],text:'month'},
 ]};
 const original=JSON.stringify(run);
 await page.goto('/workflow/ux-case/ground-truth');
 await page.getByRole('button',{name:'Expand Pipeline p1',exact:true}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog.getByTestId('preview-original-text').first()).toHaveText('left right\ndate month');
 await dialog.getByRole('button',{name:'แยกตามกรอบ DET',exact:true}).click();
 const split=dialog.getByTestId('preview-det-text').first();
 await expect(split.getByRole('button')).toHaveText(['left','right','date','month']);
 await split.getByRole('button',{name:'เลือกข้อความกรอบ DET 2',exact:true}).click();
 await expect(split.getByRole('button',{name:'เลือกข้อความกรอบ DET 2',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(dialog).toContainText('คะแนนและ Error Analysis ยังอ้างอิงข้อความต้นฉบับ');
 await dialog.getByRole('button',{name:'ข้อความต้นฉบับ',exact:true}).click();
 await expect(dialog.getByTestId('preview-original-text').first()).toHaveText('left right\ndate month');
 expect(JSON.stringify(run)).toBe(original);
 expect(state.jobPosts).toBe(0);expect(state.gtPuts).toBe(0);
});

test('text-only output does not offer fabricated DET lines',async({page})=>{
 await mockUX(page,1,{groundTruth:true});
 await page.goto('/workflow/ux-case/ground-truth');
 await page.getByRole('button',{name:'Expand Pipeline p1',exact:true}).click();
 await expect(page.getByRole('dialog').getByRole('button',{name:'แยกตามกรอบ DET',exact:true})).toBeDisabled();
});
