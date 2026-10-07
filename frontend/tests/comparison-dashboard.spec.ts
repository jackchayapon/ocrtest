import {test,expect,type Page} from "@playwright/test";
import fs from "node:fs";
import type {Comparison,Identity} from "../types/comparison";
import type {TestCase,FieldComparison,PipelineConfig} from "../types";
import {comparisonExamples} from "../lib/comparison-examples";
import {pipelineModelDisplay} from "../lib/pipeline-model-label";
import {minimumCer, testMinimumCer} from "../components/BestCer";
import {pipelineColor} from "../components/AccuracySpeedChart";

const ids=["dynamic_a","dynamic_b","disabled_old"];
const names=["โมเดลทดสอบ A · ชื่อจาก Pipeline Settings", "โมเดลทดสอบ B", "Archived configuration"];
const configs=ids.map((pipeline_id,i)=>({pipeline_id,name:names[i],enabled:i<2,source:"custom",execution_mode:"det_rec",det_model:{name:"Registered detector",version:"6",weight:"registered_weight"},rec_model:{name:"Registered recognizer",version:"5",weight:"registry_rec"}})) as PipelineConfig[];
function decision(archived=false,clear=true):Comparison {
 const pipelines:Identity[]=configs.filter(p=>archived||p.enabled).map(p=>({pipeline_id:p.pipeline_id,pipeline_name:"stale saved name",active:p.enabled,retired:!p.enabled}));
 const pair={a:ids[0],b:ids[1],documents:8,test_cases:12,mean_cer_a:.02,mean_cer_b:.12,mean_dcer_pp:-10,ci95_pp:[-12,-8] as [number,number],wins:8,ties:0,losses:0,winner:clear?ids[0]:null,verdict:clear?"clear" as const:"inconclusive" as const};
 const cells=pipelines.map(p=>({...p,cer:.05,documents:8,timed_runs:9,time_seconds:1.3}));
 const overall={recommendation:clear?ids[0]:null,ranking:pipelines.filter(p=>p.active).map(p=>({...p,score:1,mean_pair_dcer_pp:-10})),featured_pair:pair,pairs:[pair],historical_pairs:[],documents:8,cells,readiness:{x:12,y:14,documents:8,valid_pair:true,reason:null,reasons:{missing_gt:2,not_run:0,failed:0,other:0}},scatter:{points:[],common_documents:8,common_test_cases:12,cohort_mode:"common",pareto_valid:false}};
 return {scope:{},include_archived:archived,pipelines,overall,by_type:[{code:"invoice",name:"ประเภทเอกสารจาก API",archived:false,documents:8,decision:overall}],latest_results:20,minimum_documents:5,tie_pp:.05,bootstrap_samples:2000,statistical_unit:"document",computation_ms:1,actions:{missing_gt:2,missing_runs:[],failed_runs:[],short_types:[],largest_spread:[],hardest:[]}};
}
const evaluation:FieldComparison={cer:.5,wer:1,exact_match:false,character_edits:1,word_edits:1,gt_characters:2,gt_words:1,normalized_ocr:"กง",normalized_ground_truth:"กข",spans:[{kind:"equal",text:"ก"},{kind:"substitution",text:"ง",missing:"ข"}]};
function sample(id:string):TestCase {
 return {id,document_id:`doc-${id}`,document:{id:`doc-${id}`,filename:`${id}.png`,image_url:`/api/documents/doc-${id}/image`,document_type_name:"ประเภทเอกสารจาก API",width:400,height:300},roi:{x1:20,y1:30,x2:180,y2:90},page_number:2,evaluation_mode:"per_field",workflow:"global",ground_truth_raw:null,status:"confirmed",global_fields:[{id:`field-${id}`,field_index:0,roi:{x1:20,y1:30,x2:180,y2:90},source:"auto",ground_truth_raw:"กข",confirmed_at:"2026-10-07"}],runs:ids.slice(0,2).map((pipeline_id,i)=>({id:`run-${id}-${i}`,pipeline_id,pipeline_name:names[i],created_at:"2026-10-07T00:00:00Z",status:"success",final_text:i?"กง":"กข",confidence:.8,metrics:{cer:i?.5:0,wer:i?1:0,exact_match:!i},processing_time_ms:1234,boxes:[],fields:[{id:`ocr-${id}-${i}`,global_field_id:`field-${id}`,ocr_text:i?"กง":"กข",ground_truth_raw:"กข",confirmed_at:"2026-10-07",status:"success",evaluation:i?evaluation:{...evaluation,cer:0,wer:0,character_edits:0,word_edits:0,exact_match:true,normalized_ocr:"กข",spans:[{kind:"equal",text:"กข"}]}}]}))} as unknown as TestCase;
}
async function fixtures(page:Page,{clear=true,empty=false,count=3}:{clear?:boolean;empty?:boolean;count?:number}={}) {
 const list=Array.from({length:count},(_,i)=>i<3?configs[i]:{...configs[0],pipeline_id:`dynamic_${i}`,name:`Pipeline configured ${i}`,enabled:true});
 await page.route("**/api/**",async r=>{
  const url=new URL(r.request().url()),p=url.pathname;
  if(p==="/api/pipelines")return r.fulfill({json:empty?[]:list});
  if(p==="/api/analytics/comparison") {const d=decision(url.searchParams.get("include_archived")==="1",clear);if(empty){d.pipelines=[];d.latest_results=0;d.overall={...d.overall,ranking:[],recommendation:null,featured_pair:null,cells:[],pairs:[]};d.by_type=[];}else if(count>3){d.pipelines=list.filter(x=>x.enabled||d.include_archived).map(x=>({pipeline_id:x.pipeline_id,pipeline_name:x.name,active:x.enabled,retired:!x.enabled}));}return r.fulfill({json:d});}
  if(p==="/api/history")return r.fulfill({json:empty?[]:[sample("first"),sample("second")]});
  if(p.startsWith("/api/test-cases/"))return r.fulfill({json:sample(p.split("/").at(-1)!)});
  if(p==="/api/matrix")return r.fulfill({json:empty?[]:list.map(p=>({pipeline_id:p.pipeline_id,pipeline_name:p.name,tests:10,successful_runs:9,failed_runs:1,evaluated_runs:9,cer:.05,timed_runs:9,avg_time_ms:1300}))});
  if(p==="/api/analytics/pipelines")return r.fulfill({json:list.map(x=>({pipeline_id:x.pipeline_id,pipeline_name:x.name,retired:!x.enabled}))});
  if(p==="/api/analytics/summary")return r.fulfill({json:{history_cases:2}});
  if(p==="/api/document-types")return r.fulfill({json:[{id:"business",name:"ประเภทเอกสารจาก API",active:true}]});
  if(p.includes("/documents/"))return r.fulfill({contentType:"image/png",body:fs.readFileSync("public/sample-document.png")});
  return r.fulfill({json:[]});
 });
}
for(const width of [1440,1024,768,390])test(`real contracts responsive dashboard ${width}`,async({page})=>{
 await fixtures(page);await page.setViewportSize({width,height:1100});await page.goto("/matrix");
 const hero=page.getByTestId("comparison-hero");await expect(hero).toContainText(names[0]);await expect(hero).toContainText("Strong");await expect(hero).toContainText("2.0%");await expect(hero).toContainText("90.0%");await expect(hero).toContainText("1.3 sec");await expect(hero).toContainText("8 documents");
 await expect(hero).not.toContainText(/P95|95% under|Accuracy/);
 const table=page.getByRole("table",{name:"All Pipelines"});await expect(table.locator("tbody tr")).toHaveCount(2);await expect(table).not.toContainText(ids[0],{useInnerText:true});await expect(table).toContainText(names[0]);await expect(table).not.toContainText(names[2]);
 await table.locator("summary").first().click();await expect(table).toContainText("Registered detector");await expect(table).toContainText("registered_weight");await table.locator("summary").first().click();
 await expect(page.locator(".comparison-four")).toContainText("กข");await expect(page.locator(".comparison-four").getByTestId("field-error")).toContainText("ง");await expect(page.getByRole("link",{name:"เปิดภาพต้นฉบับ"})).toHaveAttribute("href",/x1=20.*page_number=2/);
 await page.getByRole("button",{name:"ตัวอย่างถัดไป"}).click();await expect(page.locator(".comparison-original")).toContainText("second.png");
 await page.getByRole("tab",{name:"Error breakdown",exact:true}).click();await expect(page.locator("#comparison-errors")).toContainText("อ่านผิด");await expect(page.locator("#comparison-errors dd").first()).toHaveText("1");
 await page.getByRole("tab",{name:"Character diff",exact:true}).click();await page.getByRole("button",{name:"ตัวอย่างก่อนหน้า"}).click();await expect(page.locator(".comparison-original")).toContainText("first.png");
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
 fs.mkdirSync("../.runtime/comparison-redesign",{recursive:true});await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:`../.runtime/comparison-redesign/dashboard-${width}.png`,fullPage:true});
});
test("N pipeline settings, archived visibility and manual pair keep decision intact",async({page})=>{
 await fixtures(page,{count:12});await page.goto("/matrix");const hero=page.getByTestId("comparison-hero"),before=await hero.innerText();
 await expect(page.getByRole("table",{name:"All Pipelines"}).locator("tbody tr")).toHaveCount(11);
 await page.getByRole("combobox",{name:"Pipeline A",exact:true}).selectOption("dynamic_11");await expect(hero).toHaveText(before,{useInnerText:true});
 await expect(page.getByRole("checkbox",{name:"Active pipelines only"})).toHaveCount(0);await expect(page.getByRole("table",{name:"All Pipelines"}).locator("tbody tr")).toHaveCount(11);await expect(hero).toHaveText(before,{useInnerText:true});
 await page.getByRole("combobox",{name:"Pipeline B",exact:true}).selectOption("dynamic_11");await expect(page.getByLabel("เปรียบเทียบสอง Pipeline โดยตรง")).toContainText("เลือก Pipeline คนละตัว");
});
test("no winner does not invent recommendation; empty has settings CTA",async({page})=>{
 await fixtures(page,{clear:false});await page.goto("/matrix");await expect(page.getByTestId("comparison-hero")).toContainText("ยังไม่มี Pipeline ที่ชนะชัดเจน");await expect(page.locator(".comparison-recommended")).toHaveCount(0);await expect(page.locator(".comparison-types")).toContainText("ยังสรุปไม่ได้");
 await fixtures(page,{empty:true});await page.reload();await expect(page.getByTestId("comparison-hero")).toContainText("ยังไม่มี Pipeline สำหรับเปรียบเทียบ");await expect(page.getByTestId("comparison-hero").getByRole("link",{name:"ไปที่ตั้งค่า Pipeline"})).toHaveAttribute("href","/settings/pipelines");
});
test("examples require identical confirmed global field, latest usable pair, never borrow labels",()=>{
 const c=sample("one");expect(comparisonExamples([c],ids[0],ids[1])).toHaveLength(1);
 c.global_fields![0].confirmed_at=null;expect(comparisonExamples([c],ids[0],ids[1])).toHaveLength(0);
 c.global_fields![0].confirmed_at="2026-10-07";c.runs[1].fields![0].global_field_id="different-field";expect(comparisonExamples([c],ids[0],ids[1])).toHaveLength(0);
 const d=sample("two");d.runs.push({...d.runs[0],created_at:"2026-10-08",status:"error"});expect(comparisonExamples([d],ids[0],ids[1])).toHaveLength(0);
});
test("CER above 100 stays honest and all error kinds remain distinguishable",async({page})=>{
 await fixtures(page,{clear:false});const d=decision(false,false);d.overall.featured_pair!.mean_cer_a=1.5;
 await page.route("**/api/analytics/comparison*",r=>r.fulfill({json:d}));
 const c=sample("errors"),e={...evaluation,character_edits:3,spans:[{kind:"equal" as const,text:"ก"},{kind:"substitution" as const,text:"ง",missing:"ข"},{kind:"insertion" as const,text:"จ"},{kind:"deletion" as const,text:"",missing:"ค"}]};c.runs[1].fields![0].evaluation=e;
 await page.route("**/api/history*",r=>r.fulfill({json:[c]}));await page.route("**/api/test-cases/*",r=>r.fulfill({json:c}));await page.goto("/matrix");
 await expect(page.getByTestId("comparison-hero")).toContainText("150.0%");const result=page.locator(".comparison-four");for(const kind of ["substitution","insertion","deletion"])await expect(result.locator(`[data-error-type=${kind}]`)).toBeVisible();
 await page.getByRole("tab",{name:"Error breakdown",exact:true}).click();await expect(page.locator("#comparison-errors dd")).toHaveText(["1","1","1"]);
 await page.getByRole("tab",{name:"Per-line view",exact:true}).click();await expect(page.locator("#comparison-errors").getByTestId("field-error")).toHaveCount(3);
});
test("legacy confirmed whole GT remains readable without saved spans",()=>{
 const c=sample("legacy");c.evaluation_mode="whole_document";c.ground_truth_raw="กข";c.global_fields=[];c.runs.forEach(r=>{r.fields=[];});
 const examples=comparisonExamples([c],ids[0],ids[1]);expect(examples).toHaveLength(1);expect(examples[0].gt).toBe("กข");expect(examples[0].evaluationA).toBeNull();
 c.status="tested";expect(comparisonExamples([c],ids[0],ids[1])).toHaveLength(0);
});

test("official configuration display follows separate DET/REC selections, not pipeline name",async({page})=>{
 await fixtures(page);
 const official={...configs[0],source:"official",execution_mode:"integrated",name:"Display name says REC V6 but config selects V5",det_model:null,rec_model:null,integrated_options:{paddle_model_defaults:false,det_version:"6",rec_version:"5",det_weight:"baseline",rec_weight:"thai_ft_v1"}} as PipelineConfig;
 await page.route("**/api/pipelines",r=>r.fulfill({json:[official,configs[1]]}));
 await page.goto("/matrix");
 const row=page.getByRole("table",{name:"All Pipelines"}).locator("tbody tr").first();
 await row.locator("summary").click();
 await expect(row).toContainText("PP-OCRv6_medium_det");
 await expect(row).toContainText("th_PP-OCRv5_mobile_rec");
 await expect(row).toContainText("Version: 5 · Weight: thai_ft_v1");
 const defaults={...official,integrated_options:{...official.integrated_options!,paddle_model_defaults:true}};
 expect(pipelineModelDisplay(defaults,"rec").version).toBeNull();
 expect(pipelineModelDisplay(defaults,"rec").summary).toBe("ตามค่า env ของ Gateway");
});

test("examples retain canonical OCR order and GT evaluation prediction",()=>{
 const c=sample("order");c.evaluation_mode="whole_document";c.ground_truth_raw="Left Right\nNext row";
 c.runs[0].final_text="Left Right\nNext row";
 c.runs[0].document_evaluation={...evaluation,prediction:"Left Right Next row",mode:"whole_document",evaluated_at:"2026-10-07T00:00:00Z"};
 expect(comparisonExamples([c],ids[0],ids[1])[0].textA).toBe("Left Right Next row");
 c.runs[0].document_evaluation=null;
 expect(comparisonExamples([c],ids[0],ids[1])[0].textA).toBe("Left Right\nNext row");
 c.evaluation_mode="per_field";c.global_fields![0].confirmed_at=null;
 expect(comparisonExamples([c],ids[0],ids[1])).toEqual([]);
});

for(const state of ["no OCR", "no GT", "no matched pair"])test(`comparison empty state: ${state}`,async({page})=>{
 await fixtures(page);
 const c=sample("empty-example");
 if(state==="no OCR")c.runs=[];
 if(state==="no GT")c.global_fields![0].confirmed_at=null;
 if(state==="no matched pair")c.runs=c.runs.slice(0,1);
 await page.route("**/api/history*",r=>r.fulfill({json:[c]}));
 await page.goto("/matrix");
 await expect(page.locator("#compare-results .comparison-empty")).toBeVisible();
 await expect(page.locator(".comparison-four")).toHaveCount(0);
});

test("fresh detail eligibility overrides stale history GT",async({page})=>{
 await fixtures(page);const c=sample("first");c.global_fields![0].confirmed_at=null;
 await page.route("**/api/test-cases/first",r=>r.fulfill({json:c}));
 await page.goto("/matrix");
 await expect(page.locator("#compare-results .comparison-empty")).toBeVisible();
 await expect(page.locator(".comparison-four")).toHaveCount(0);
});

test("matched documents outside the History page keep honest empty copy and pagination",async({page})=>{
 await fixtures(page);
 const d=decision();d.overall.featured_pair!.documents=5;
 await page.route("**/api/analytics/comparison*",r=>r.fulfill({json:d}));
 const unavailable=Array.from({length:21},(_,i)=>{const c=sample(`unconfirmed-${i}`);c.global_fields![0].confirmed_at=null;return c;});
 await page.route("**/api/history*",r=>r.fulfill({json:new URL(r.request().url()).searchParams.get("offset")==="20"?[sample("next-page")]:unavailable}));
 await page.goto("/matrix");
 const empty=page.locator("#compare-results .comparison-empty");
 await expect(empty).toContainText("ยังไม่พบตัวอย่างที่พร้อมเปรียบเทียบในหน้าประวัติปัจจุบัน");
 await expect(empty).toContainText("ระบบมีเอกสารที่เทียบตรงกัน 5 ฉบับ");
 await expect(empty).not.toContainText("ยังไม่มีเอกสารชุดเดียวกันที่ Pipeline ทั้งสองมีผลพร้อมเปรียบเทียบ");
 await page.getByRole("button",{name:"ดูตัวอย่างจากหน้าถัดไป"}).click();
 await expect(page.locator(".comparison-four")).toBeVisible();
 await expect(page.locator(".comparison-original")).toContainText("next-page.png");
});

test("zero matched documents retain true-zero empty copy",async({page})=>{
 await fixtures(page);const d=decision();d.overall.featured_pair!.documents=0;
 await page.route("**/api/analytics/comparison*",r=>r.fulfill({json:d}));
 await page.route("**/api/history*",r=>r.fulfill({json:[]}));
 await page.goto("/matrix");
 const empty=page.locator("#compare-results .comparison-empty");
 await expect(empty).toContainText("ยังไม่มีเอกสารชุดเดียวกันที่ Pipeline ทั้งสองมีผลพร้อมเปรียบเทียบ");
 await expect(empty).toContainText("ต้องมี Ground Truth ที่ยืนยันแล้วและผลสำเร็จของทั้งสอง Pipeline");
 await expect(empty).not.toContainText("ระบบมีเอกสารที่เทียบตรงกัน");
});

for(const field of [true,false])test(`paired, overall and ${field?"field":"document"} CER have distinct scopes`,async({page})=>{
 await fixtures(page);
 const d=decision();d.overall.featured_pair!.mean_cer_a=.031;d.overall.featured_pair!.mean_cer_b=.142;d.overall.featured_pair!.mean_dcer_pp=-11.1;
 d.overall.cells[0].cer=.087;
 d.by_type[0].decision={...d.overall,featured_pair:{...d.overall.featured_pair!,mean_cer_a:.024}};
 await page.route("**/api/analytics/comparison*",r=>r.fulfill({json:d}));
 const c=sample("scope");
 if(!field){c.evaluation_mode="whole_document";c.ground_truth_raw="กข";c.global_fields=[];}
 await page.route("**/api/history*",r=>r.fulfill({json:[c]}));await page.route("**/api/test-cases/*",r=>r.fulfill({json:c}));
 await page.goto("/matrix");
 const hero=page.getByTestId("comparison-hero");
 const paired=hero.locator(".comparison-metric").filter({hasText:"Paired CER"});
 await expect(paired).toContainText("3.1%");await expect(paired).toContainText("เอกสารที่คู่หลักมีผลพร้อมเทียบ");
 const ranking=page.getByRole("table",{name:"All Pipelines"});
 await expect(ranking.getByRole("columnheader",{name:"Overall CER ↓",exact:true})).toBeVisible();
 await expect(ranking.locator('tbody tr').first().locator('[data-label="Overall CER"]')).toHaveText("8.7%");
 await expect(page.locator(".comparison-ranking")).toContainText("จึงอาจต่างจาก Paired CER");
 await expect(page.locator(".comparison-four footer").first()).toContainText(`${field?"This field CER":"This document CER"} 0.0%`);
 await expect(page.getByTestId("hero-paired-evidence")).toContainText("14.2%");await expect(page.getByTestId("hero-paired-evidence")).toContainText("-11.10 pp");
 await expect(page.locator(".comparison-types")).toContainText("Type paired CER");await expect(page.locator(".comparison-types")).toContainText("2.4%");
 await expect(page.locator(".comparison-disagreement-heading")).toContainText("Example CER");
 await expect(page.locator("#comparison-errors")).toContainText(field?"This field":"This document");
});

for(const state of ["Strong","Moderate","Limited","Insufficient"] as const)test(`evidence strength ${state} follows paired verdict and minimum`,async({page})=>{
 await fixtures(page);const d=decision(false,state==="Strong");
 if(state==="Limited"){d.overall.featured_pair!.documents=3;d.overall.featured_pair!.verdict="insufficient";}
 if(state==="Insufficient"){d.overall.featured_pair=null;d.overall.readiness.valid_pair=false;}
 await page.route("**/api/analytics/comparison*",r=>r.fulfill({json:d}));await page.goto("/matrix");
 await expect(page.getByTestId("evidence-strength")).toHaveText(state);
 await expect(page.locator(".comparison-evidence")).toContainText("ขั้นต่ำ 5");
 await expect(page.getByRole("img",{name:/ระดับหลักฐานจากเอกสาร/})).toHaveAttribute("title",/ไม่ใช่ Model confidence/);
 if(state!=="Strong")await expect(page.getByTestId("evidence-strength")).not.toHaveText("Strong");
});

test("Comparison ignores old query scope and shows no filters or pair tables",async({page})=>{
 const requests:URL[]=[];page.on("request",r=>{const u=new URL(r.url());if(u.pathname.startsWith("/api/"))requests.push(u);});
 await fixtures(page);await page.goto("/matrix?document_type_id=old&pipeline=disabled_old&date_from=2020-01-01&date_to=2020-02-01&include_archived=1&search=hidden");
 await expect(page.getByTestId("comparison-hero")).toContainText(names[0]);
 await expect.poll(()=>new URL(page.url()).search).toBe("");
 for(const label of ["ประเภทเอกสาร (ธุรกิจ)","ช่วงเวลา","Pipeline"]){await expect(page.getByRole("combobox",{name:label,exact:true})).toHaveCount(0);}
 await expect(page.getByRole("checkbox",{name:"Active pipelines only"})).toHaveCount(0);await expect(page.getByRole("button",{name:"Filters",exact:true})).toHaveCount(0);
 expect(requests.length).toBeGreaterThan(0);for(const u of requests)for(const key of ["document_type_id","pipeline","date_from","date_to","search"])expect(u.searchParams.has(key)).toBe(false);
 await page.getByText("Advanced evaluation details",{exact:true}).click();
 await expect(page.getByText("รายละเอียดการเทียบเป็นคู่",{exact:true})).toHaveCount(0);await expect(page.getByRole("table",{name:"หลักฐานการเทียบคู่"})).toHaveCount(0);
 await expect(page.getByRole("combobox",{name:"Pipeline A",exact:true})).toBeVisible();
});

test("unassigned is excluded everywhere and only minimum descriptive type CER is highlighted",async({page})=>{
 await fixtures(page);const d=decision(false,false);d.overall.cells[0].cer=.037;d.overall.cells[1].cer=.042;
 d.by_type.push({...d.by_type[0],code:"unassigned",name:"Unassigned must stay hidden"});
 await page.route("**/api/analytics/comparison*",r=>r.fulfill({json:d}));await page.goto("/matrix");
 await expect(page.locator(".comparison-types")).not.toContainText("Unassigned must stay hidden");
 await page.getByRole("tab",{name:"ตามประเภทเอกสาร",exact:true}).click();await expect(page.locator("main")).not.toContainText("Unassigned must stay hidden");
 await page.getByText("ดูตารางทุก Pipeline",{exact:true}).click();const row=page.getByRole("table",{name:"เปรียบเทียบตามประเภทเอกสาร"}).locator("tbody tr").first();
 await expect(row.locator(".comparison-cer-best")).toHaveCount(1);await expect(row.locator(".comparison-cer-best")).toContainText("Type overall CER 3.7%");
 await expect(row.locator(".comparison-best-badge")).toHaveText("CER ต่ำสุด");await expect(row.locator(".badge.info")).toHaveCount(0);
});

for(const tied of [false,true])test(`per-test minimum CER excludes failures and missing runs in both views: tie=${tied}`,async({page})=>{
 await fixtures(page,{count:7});const d=decision();d.pipelines=Array.from({length:7},(_,i)=>({pipeline_id:`p${i}`,pipeline_name:`Configured ${i}`,active:true,retired:false}));
 await page.route("**/api/analytics/comparison*",r=>r.fulfill({json:d}));const c=sample("best-row");
 c.runs=[.037,tied?.037:.042,.061,.073,null,.038,.001].flatMap((cer,i)=>cer===null?[]:[{...c.runs[0],id:`r${i}`,pipeline_id:`p${i}`,status:i===6?"error":"success",metrics:{cer,wer:1,exact_match:false}}]);
 await page.route("**/api/history*",r=>r.fulfill({json:[c]}));await page.goto("/matrix");
 for(const view of ["สรุปผล","ตามประเภทเอกสาร"]){
  await page.getByRole("tab",{name:view,exact:true}).click();const summary=page.locator("details>summary").filter({hasText:"เปรียบเทียบรายชุดทดสอบ"});if(!await summary.locator("..").evaluate(e=>e.hasAttribute("open")))await summary.click();
  const row=page.getByRole("table",{name:"เปรียบเทียบรายชุดทดสอบ"}).locator("tbody tr");
  await expect(row.locator(".comparison-cer-best")).toHaveCount(tied?2:1);await expect(row.locator(".comparison-best-badge")).toHaveText(tied?["ร่วมดีที่สุด","ร่วมดีที่สุด"]:["ดีที่สุดในเอกสารนี้"]);
  await expect(row.locator("td").nth(6)).not.toHaveClass(/comparison-cer-best/);await expect(row.locator(".comparison-cer-error")).toContainText("ประมวลผลไม่สำเร็จ");await expect(row.locator(".comparison-cer-missing")).toContainText("ยังไม่ทดสอบ");
 }
});

test("CER minima accept zero, ignore invalid values, and stable colors follow identity",()=>{
 expect(minimumCer([null,NaN,Infinity,-1,0,.01])).toEqual({minimum:0,tied:false});expect(minimumCer([.037,.037])).toEqual({minimum:.037,tied:true});
 const c=sample("error");c.runs.forEach(r=>r.status="error");expect(testMinimumCer(c,ids).minimum).toBeNull();
 expect(pipelineColor(ids[0])).toBe(pipelineColor(ids[0]));expect(new Set(ids.map(pipelineColor)).size).toBe(ids.length);
});

test("type descriptive ties highlight every minimum without inventing recommendation",async({page})=>{
 await fixtures(page);const d=decision(false,false);await page.route("**/api/analytics/comparison*",r=>r.fulfill({json:d}));await page.goto("/matrix?view=by-type");await page.getByText("ดูตารางทุก Pipeline",{exact:true}).click();
 const row=page.getByRole("table",{name:"เปรียบเทียบตามประเภทเอกสาร"}).locator("tbody tr").first();await expect(row.locator(".comparison-cer-best")).toHaveCount(2);await expect(row.locator(".comparison-best-badge")).toHaveText(["ร่วมต่ำสุด","ร่วมต่ำสุด"]);await expect(row.locator(".badge.info")).toHaveCount(0);
});

for(const width of [1440,1024,768,390])test(`Accuracy Speed axes, grid, identity, legend and backend Pareto ${width}`,async({page})=>{
 await fixtures(page);const d=decision();d.overall.scatter.pareto_valid=true;d.overall.scatter.points=d.overall.cells.map((c,i)=>({...c,cer:i?.061:.037,time_seconds:i?.9:1.2,filled:true,pareto:true,cohort_mode:"common"}));
 await page.route("**/api/analytics/comparison*",r=>r.fulfill({json:d}));await page.setViewportSize({width,height:1100});await page.goto("/matrix");
 await page.getByText("Advanced evaluation details",{exact:true}).click();await page.locator("summary").filter({hasText:"ความแม่นยำ × ความเร็ว"}).click();
 const chart=page.getByLabel("ความแม่นยำ × ความเร็ว",{exact:true});await expect(chart.getByTestId("chart-axes")).toBeVisible();await expect(chart.getByTestId("chart-grid")).toHaveCount(10);
  await expect(chart.getByTestId("chart-marker")).toHaveCount(2);await expect(chart.getByTestId("pareto-frontier")).toBeVisible();
  await expect(chart.getByTestId("distribution-guide")).toHaveCount(0);
 for(const n of names.slice(0,2))await expect(chart.locator(".comparison-speed-legend")).toContainText(n);
 await expect(chart.getByTestId("chart-marker").first()).toHaveAttribute("aria-label",/CER.*วินาที.*เอกสาร/);await chart.getByTestId("chart-marker").first().focus();await expect(chart.getByRole("status")).toContainText(names[0]);
 await expect(chart).toContainText("CER เฉลี่ย (%)");await expect(chart).toContainText("เวลาเฉลี่ยต่อชุดทดสอบ (วินาที)");
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
 fs.mkdirSync("../.runtime/comparison-ux",{recursive:true});await chart.screenshot({path:`../.runtime/comparison-ux/chart-${width}.png`});
});

for(const scenario of ["invalid","single","one-pareto"] as const)test(`chart visible guide fallback: ${scenario}`,async({page})=>{
 await fixtures(page);const d=decision();d.overall.scatter.pareto_valid=scenario==="one-pareto";
 d.overall.scatter.points=d.overall.cells.map((c,i)=>({...c,cer:i?.061:.037,time_seconds:i?.9:1.2,filled:true,pareto:i===0,cohort_mode:"common"}));
 if(scenario==="single")d.overall.scatter.points=d.overall.scatter.points.slice(0,1);
 await page.route("**/api/analytics/comparison*",r=>r.fulfill({json:d}));await page.setViewportSize({width:390,height:1100});await page.goto("/matrix");
 await page.getByText("Advanced evaluation details",{exact:true}).click();await page.locator("summary").filter({hasText:"ความแม่นยำ × ความเร็ว"}).click();
 const chart=page.getByLabel("ความแม่นยำ × ความเร็ว",{exact:true});await expect(chart.getByTestId("pareto-frontier")).toHaveCount(0);
 if(scenario==="single"){
  await expect(chart.getByTestId("distribution-guide")).toHaveCount(0);await expect(chart.getByTestId("distribution-guide-legend")).toHaveCount(0);
 }else{
  const guide=chart.getByTestId("distribution-guide");await expect(guide).toBeVisible();await expect(guide).toHaveAttribute("stroke","#94a3b8");await expect(guide).toHaveAttribute("vector-effect","non-scaling-stroke");
  await expect(chart.getByTestId("distribution-guide-legend")).toHaveText("เส้นช่วยอ่านกราฟ (ไม่ใช่ Pareto)");await expect(chart.getByText("แนว Pareto",{exact:true})).toHaveCount(0);
  const xs=(await guide.getAttribute("points"))!.split(" ").map(p=>Number(p.split(",")[0]));expect(xs).toEqual([...xs].sort((a,b)=>a-b));expect(xs).toHaveLength(2);
  fs.mkdirSync("../.runtime/comparison-ux",{recursive:true});await chart.screenshot({path:`../.runtime/comparison-ux/guide-${scenario}-390.png`});
 }
});

test("chart keeps incomplete pipelines in legend without inventing points or Pareto",async({page})=>{
 await fixtures(page);const d=decision();d.overall.scatter.points=d.overall.cells.map(c=>({...c,cer:null,time_seconds:null,filled:false,pareto:true,cohort_mode:"own"}));
 await page.route("**/api/analytics/comparison*",r=>r.fulfill({json:d}));await page.goto("/matrix");await page.getByText("Advanced evaluation details",{exact:true}).click();await page.locator("summary").filter({hasText:"ความแม่นยำ × ความเร็ว"}).click();
 await expect(page.locator(".comparison-speed")).toContainText("ยังไม่มีผลที่มีทั้ง CER และเวลา");await expect(page.getByTestId("chart-marker")).toHaveCount(0);await expect(page.getByTestId("pareto-frontier")).toHaveCount(0);await expect(page.locator(".comparison-speed-legend li")).toHaveCount(2);
});
