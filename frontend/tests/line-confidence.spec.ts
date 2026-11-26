import {test,expect} from '@playwright/test';
import type {PipelineRun} from '../types';
import {lineConfidences} from '../lib/line-confidence';
import {mockUX} from './ux-stability-fixture';

function run(text:string,boxes:unknown[],confidence:number|null=.5){
 return {status:'success',final_text:text,fields:[{confidence,diagnostics:{boxes}}]} as unknown as PipelineRun;
}

test('recognition scores follow text lines including merged OpenThai segments',()=>{
 expect(lineConfidences(run('one two\nthree',[
  {text:'one',confidence:.8},{text:'two',confidence:1},{text:'three',rec_confidence:.6,det_confidence:.99},
 ]))).toEqual([.9,.6]);
 expect(lineConfidences(run('a\r\n\r\nb',[
  {text:'a',confidence:0},{text:'b',confidence:null},
 ]))).toEqual([0,null,null]);
 expect(lineConfidences(run('a\nb',[{text:'b',confidence:1},{text:'a',confidence:1}]))).toEqual([null,null]);
 expect(lineConfidences(run('a\nb',[]))).toEqual([null,null]);
 expect(lineConfidences(run('a',[]))).toEqual([.5]);
});

test('evaluation displays whole and per-line confidence separately',async({page})=>{
 const state=await mockUX(page,1,{groundTruth:true});
 state.record.global_fields[0].roi={x1:0,y1:0,x2:600,y2:400};
 state.record.ground_truth_raw='a\nb';
 state.record.global_fields[0].ground_truth_raw='a\nb';
 state.record.runs.forEach(r=>{
  r.final_text='a\nb';
  Object.assign(r,{confidence:.85});
  r.fields[0].diagnostics={boxes:[{text:'a',confidence:.8},{text:'b',confidence:.9}]};
 });
 await page.goto('/workflow/ux-case/ground-truth');
 const metrics=page.getByTestId('global-metrics-p1');
 await expect(metrics.first()).toContainText('85.00%');
 await page.getByRole('button',{name:'Sub-fields',exact:true}).click();
 await expect(metrics).toHaveCount(2);
 await expect(metrics.nth(0)).toContainText('80.00%');
 await expect(metrics.nth(1)).toContainText('90.00%');
});
