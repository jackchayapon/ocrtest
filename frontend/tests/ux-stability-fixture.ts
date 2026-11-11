import type {Page} from '@playwright/test';

export const limits={max_upload_mb:10,max_image_pixels:2000000,max_image_dimension:8000,max_pdf_pages:20,pdf_render_dpi:140,max_job_fields:80,max_job_pipelines:3,max_job_units:240};
const svg='<svg xmlns="http://www.w3.org/2000/svg" width="600" height="400"><rect width="600" height="400" fill="white"/><rect x="10" y="10" width="80" height="30" fill="blue"/><text x="15" y="25">Synthetic</text></svg>';
const evaluation={cer:1/3,wer:1,exact_match:false,character_edits:1,word_edits:1,gt_characters:3,gt_words:1,normalized_ocr:'ก😀',normalized_ground_truth:'ก้😀',spans:[{kind:'equal',text:'ก'},{kind:'deletion',text:'',missing:'้'},{kind:'equal',text:'😀'}]};

export async function mockUX(page:Page,count=2,options:{groundTruth?:boolean;configGate?:Promise<void>;configFailures?:number;pdf?:boolean}={}){
 const fields=Array.from({length:count},(_,i)=>({id:`f${i+1}`,field_index:i+1,roi:{x1:i%8*75+5,y1:Math.floor(i/8)*40+5,x2:i%8*75+65,y2:Math.floor(i/8)*40+35},source:'manual',ground_truth_raw:'ก้😀',confirmed_at:options.groundTruth?'2026-11-11':null}));
 const runs=['p1','p2','p3'].map(id=>({id:'r'+id,pipeline_id:id,pipeline_name:'Pipeline '+id,status:'success',final_text:'ก😀',document_evaluation:evaluation,fields:fields.map(f=>({id:id+f.id,global_field_id:f.id,field_index:f.field_index,status:'success',ocr_text:'ก😀',evaluation,confidence:.9,diagnostics:{}}))}));
 const record={id:'ux-case',workflow:'global',categories:[],ground_truth_raw:fields.map(f=>f.ground_truth_raw).join('\n'),evaluation_mode:'per_field',layout_confirmed_at:'2026-11-11',updated_at:'2026-11-11T00:00:00Z',gt_prefill:{status:'partial'},global_fields:fields,document:{id:'ux-doc',filename:'synthetic'+(options.pdf?'.pdf':'.png'),width:600,height:400,document_type:options.pdf?'pdf':'image',page_number:options.pdf?2:null,page_count:options.pdf?3:1,image_url:'/api/ux-preview.svg'},runs:options.groundTruth?runs:[]};
 const state={record,configRequests:0,configFailures:options.configFailures??0,autoCalls:0,autoRegions:25,jobPosts:0,jobExists:false,phase:'running',resultsReady:true,resultReads:0,imageCalls:0,imageStatuses:[] as number[],insights:[] as string[],crops:[] as string[],uploadAttempts:0,acceptedUploads:0,uploadMode:'normal',gtPuts:0};
 const job=()=>({job_id:'ux-job',test_case_id:record.id,status:state.phase==='completed'?'completed':'running',pipeline_ids:['p1','p2','p3'],total_fields:count,total_pipelines:3,completed_units:state.phase==='running'?1:count*3,failed_units:0,completed_pipelines:state.phase==='running'?0:3,progress_percent:state.phase==='running'?Math.round(100/(count*3)):100,current_pipeline_id:state.phase==='prefill'?'system_gt_prefill':'p1',current_field_index:state.phase==='prefill'?4:1,started_at:'2026-11-11T00:00:00Z',finished_at:state.phase==='completed'?'2026-11-11T00:01:00Z':null,created_at:'2026-11-11T00:00:00Z',run_ids:runs.map(r=>r.id)});
 const cors={'Access-Control-Allow-Origin':'*','Access-Control-Expose-Headers':'Retry-After, X-OCRLab-Retry-Safe'};
 await page.route('**/api/**',async route=>{
  const request=route.request(),url=new URL(request.url()),path=url.pathname;
  if(path.endsWith('/upload-config')){state.configRequests++;if(options.configGate)await options.configGate;if(state.configFailures-->0)return route.fulfill({status:503,json:{detail:'Configuration unavailable'}});return route.fulfill({json:limits});}
  if(path.endsWith('/pipelines'))return route.fulfill({json:['p1','p2','p3'].map(id=>({pipeline_id:id,name:'Pipeline '+id,enabled:true}))});
  if(path.endsWith('/document-types'))return route.fulfill({json:[]});
  if(path.endsWith('/auto-rois')){state.autoCalls++;await new Promise(r=>setTimeout(r,200));return route.fulfill({json:{regions:Array.from({length:state.autoRegions},(_,i)=>({roi:{x1:10+i,y1:100,x2:50+i,y2:130},source:'auto'}))}});}
  if(path.endsWith('/jobs')){if(request.method()==='POST'){state.jobPosts++;state.jobExists=true;return route.fulfill({status:202,json:job()});}return route.fulfill({json:state.jobExists?job():null});}
  if(path.endsWith('/ocr-jobs/ux-job'))return route.fulfill({json:job()});
  if(path.endsWith('/ocr-jobs/ux-job/results')){state.resultReads++;return route.fulfill({json:{test_case_id:record.id,runs:state.resultsReady?runs:[]}});}
  if(path.endsWith('/global-fields')&&request.method()==='PUT'){record.global_fields=request.postDataJSON().fields;return route.fulfill({json:record});}
  if(path.endsWith('/global-ground-truth')){state.gtPuts++;return route.fulfill({json:record});}
  if(path.endsWith('/error-summary')){
   state.insights.push(url.toString());const f=fields.find(f=>f.id===url.searchParams.get('field_id'))??fields[0];
   const stats={character_edits:1,substitution:0,deletion:1,insertion:0,characters:[{character:'้',display:'◌้',name:'ไม้โท',code_point:'U+0E49',total:1,substitution:0,deletion:1,insertion:0}],confusion_pairs:[{expected:'้',predicted:'',count:1}]};
   return route.fulfill({json:{document_id:'ux-doc',page_number:options.pdf?2:null,test_case_id:record.id,evaluation_mode:'per_field',pipelines:[{pipeline_id:url.searchParams.get('pipeline_id'),pipeline_name:'Pipeline '+url.searchParams.get('pipeline_id'),statistics:stats,evaluated_scopes:1,total_scopes:1,scopes:[{state:'ready',field_index:f.field_index,global_field_id:f.id,roi:f.roi,display_ground_truth:'ก้😀',display_ocr_text:'ก😀',details:[{error_type:'deletion',ground_truth_unit:'้',ocr_unit:null,ground_truth_excerpt:'ก้😀',ocr_excerpt:'ก😀',ocr_highlight:{start:1,length:0},explanation:'อ่านขาดหาย ไม้โท'}]}]}]}});
  }
  if(path.endsWith('/documents')&&request.method()==='POST'){
   state.uploadAttempts++;
   if(state.uploadMode==='safe'||state.uploadMode==='once'&&state.uploadAttempts===1)return route.fulfill({status:429,headers:{...cors,'Retry-After':'1','X-OCRLab-Retry-Safe':'pre-admission'},json:{detail:'Image busy'}});
   if(state.uploadMode==='ambiguous'){state.acceptedUploads++;return route.abort('failed');}
   if(state.uploadMode==='unsafe')return route.fulfill({status:503,json:{detail:'Unknown acceptance'}});
   state.acceptedUploads++;return route.fulfill({status:201,json:record.document});
  }
  if(path.endsWith('ux-preview.svg')||path.endsWith('/image')||path.endsWith('/crop')){
   state.imageCalls++;if(path.endsWith('/crop')||path.endsWith('/image'))state.crops.push(url.toString());
   const status=state.imageStatuses.shift()??200;
   if(status!==200)return route.fulfill({status,headers:{...cors,'Retry-After':'0'},json:{detail:'Synthetic preview unavailable'}});
   return route.fulfill({contentType:'image/svg+xml',headers:cors,body:svg});
  }
  if(path.includes('/test-cases/ux-case')){if(state.phase==='completed')record.runs=runs;return route.fulfill({json:record});}
  if(path==='/api/documents/ux-doc')return route.fulfill({json:record.document});
  return route.fulfill({json:[]});
 });
 return state;
}
