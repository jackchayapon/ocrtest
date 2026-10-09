"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import {useRouter,useSearchParams} from "next/navigation";
import {useEffect,useRef,useState} from "react";
import {LoaderCircle,X} from "lucide-react";
import * as api from "@/lib/api";
import type {EvaluationMode,GlobalField,PipelineConfig,ROI,TestCase} from "@/types";
import {PageHeader} from "./ConsoleUI";
import {pipelineLabel,userError} from "@/lib/i18n/th";
import {previewFieldOrder} from "@/lib/global-order";
import {completeGT,fieldLineCounts,joinFieldGT,splitDocumentGT} from "@/lib/ground-truth-sync";
import WorkflowSteps,{stageTitles,stages,workflowUrl,type WorkflowStage} from "./WorkflowSteps";
import GlobalGroundTruthForm from "./GlobalGroundTruthForm";
import GlobalFieldEvaluation from "./GlobalFieldEvaluation";
const DocumentViewer=dynamic(()=>import("./DocumentViewer"),{ssr:false});
const fieldName=(f:GlobalField)=>`Field ${String(f.field_index).padStart(2,"0")}`;

export default function GlobalWorkspace({initialCase,stage}:{initialCase:TestCase;stage:WorkflowStage}){
 const router=useRouter(),[saved,setSaved]=useState(initialCase),[fields,setFields]=useState(initialCase.global_fields??[]);
 const [activeId,setActiveId]=useState<string|null>(stage==="layout"?null:((stage==="ground-truth"?fields.find(f=>f.confirmed_at)?.id:undefined)??fields[0]?.id??null));
 const [drawing,setDrawing]=useState(false);
 const [configs,setConfigs]=useState<PipelineConfig[]>([]),[pipelineIds,setPipelineIds]=useState<string[]>([]);
 const [mode,setMode]=useState<EvaluationMode>(saved.evaluation_mode??"per_field"),[documentGT,setDocumentGT]=useState(saved.ground_truth_raw??"");
 const [lineCounts,setLineCounts]=useState(()=>fieldLineCounts(fields));
 const [busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState(false);
 const [saveMessage,setSaveMessage]=useState("");
 const searchParams=useSearchParams();
 const [comparison,setComparison]=useState(searchParams.get("edit")!=="1"&&initialCase.runs.some(r=>r.document_evaluation||r.fields?.some(f=>f.evaluation)));
 const actionPending=useRef(false);
 const fieldRows=useRef(new Map<string,HTMLDivElement>());
 const doc=saved.document,active=fields.find(f=>f.id===activeId)??null,locked=stage!=="layout"&&!!saved.layout_confirmed_at,hasRuns=!!saved.runs.length;
 const latestRuns=[...new Set(saved.runs.map(r=>r.pipeline_id))].flatMap(id=>{const r=[...saved.runs].reverse().find(r=>r.pipeline_id===id);return r?[r]:[];});
 useEffect(()=>{let alive=true;api.getPipelines().then(p=>{if(alive){setConfigs(p);setPipelineIds(initialCase.runs.length?[...new Set(initialCase.runs.map(r=>r.pipeline_id))].filter(id=>p.some(c=>c.pipeline_id===id&&c.enabled)):p.filter(c=>c.enabled).map(c=>c.pipeline_id));}}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[initialCase]);
 async function act(fn:()=>Promise<void>){if(actionPending.current)return;actionPending.current=true;setBusy(true);setError("");setNotice(false);setSaveMessage("");try{await fn();}catch(e){setError(userError(e instanceof Error?e.message:"ดำเนินการไม่สำเร็จ"));}finally{actionPending.current=false;setBusy(false);}}
 function adopt(c:TestCase){setSaved(c);setFields(c.global_fields??[]);const ids=new Set(c.global_fields?.map(f=>f.id));setActiveId(old=>old&&ids.has(old)?old:null);}
 function selectField(id:string){if(busy)return;setDrawing(false);setActiveId(id);}
 function selectPreviewField(id:string){selectField(id);if(!busy)fieldRows.current.get(id)?.scrollIntoView({block:"nearest",inline:"nearest",behavior:"smooth"});}
 function deleteField(id:string){if(locked||busy)return;setFields(old=>previewFieldOrder(old.filter(f=>f.id!==id)));setActiveId(old=>old===id?null:old);setSaveMessage("");setDrawing(false);}
 function add(roi:ROI,source:"auto"|"manual"){
  if(locked||busy)return;const f:GlobalField={id:crypto.randomUUID(),field_index:fields.length+1,roi,source,ground_truth_raw:null,confirmed_at:null};setFields(old=>previewFieldOrder([...old,f]));setActiveId(f.id);setSaveMessage("");
 }
 function edit(roi:ROI|null){if(locked||busy||!active||!roi)return;setFields(old=>previewFieldOrder(old.map(f=>f.id===active.id?{...f,roi}:f)));setSaveMessage("");}
 function changeDocument(text:string,counts=lineCounts){setDocumentGT(text.replace(/\r\n?/g,"\n"));setFields(splitDocumentGT(text,fields,counts));setLineCounts(counts);setNotice(false);setSaveMessage("");}
 function changeField(field:GlobalField){const next=fields.map(f=>f.id===field.id?field:f);setFields(next);setDocumentGT(joinFieldGT(next));setLineCounts(fieldLineCounts(next));setNotice(false);setSaveMessage("");}
 async function saveGT(calculate:boolean){if(calculate&&!completeGT(fields,documentGT)){setError("กรุณากรอก GT ให้ครบทุก Field และตรวจการแบ่งข้อความก่อนคำนวณ");return;}await act(async()=>{
  let c=saved;for(const f of fields)if(f.ground_truth_raw!==saved.global_fields?.find(s=>s.id===f.id)?.ground_truth_raw)c=await api.saveGlobalGT(c.id,f);
  if(documentGT!==(saved.ground_truth_raw??""))c=await api.saveGroundTruth(c.id,documentGT,false);
  if(c.evaluation_mode!==mode)c=await api.setEvaluationMode(c.id,mode);adopt(c);
  if(calculate){adopt(await api.evaluateGlobal(c.id,"auto",fields.map(f=>f.id),true));setNotice(true);setComparison(true);}
  else setSaveMessage("บันทึก GT ฉบับร่างแล้ว — ยังไม่ได้คำนวณผลประเมิน");
 });}
 const allowed=stage==="layout"||stage==="pipelines"&&locked||(stage==="ground-truth")&&hasRuns;
 const layoutDirty=JSON.stringify(fields)!==JSON.stringify(saved.global_fields??[]);
 async function saveLayout(confirmed:boolean){
  if(hasRuns||saved.layout_locked_at){
   if(!layoutDirty)return saved;
   const revision=await api.createTestCase({workflow:"global",document_id:doc.id,page_number:doc.page_number,roi:null,ground_truth_raw:null,category_codes:saved.categories.map(c=>c.code)});
   return api.saveGlobalLayout(revision.id,fields.map(f=>({...f,id:crypto.randomUUID()})),confirmed);
  }
  return api.saveGlobalLayout(saved.id,fields,confirmed);
 }
 const fieldList=<div className="max-h-[min(50vh,28rem)] space-y-2 overflow-y-auto overscroll-contain p-1 [scrollbar-gutter:stable]" tabIndex={0} role="region" aria-label="Global Fields">{fields.map(f=><div key={f.id} ref={node=>{if(node)fieldRows.current.set(f.id,node);else fieldRows.current.delete(f.id);}} className={`flex items-center gap-2 rounded-lg border p-2 ${f.id===activeId?"border-indigo-400 bg-indigo-50":"border-slate-200"}`}>
 <button type="button" data-testid="global-field-nav" disabled={busy} className="flex-1 text-left text-sm" aria-pressed={f.id===activeId} onClick={()=>selectField(f.id)}>{fieldName(f)}{f.confirmed_at?" ✓":""}</button>
 {!locked&&<button type="button" className="rounded-md p-2 text-slate-500 hover:bg-red-50 hover:text-red-700 disabled:opacity-40" disabled={busy} aria-label={`ลบ ${fieldName(f)}`} title={`ลบ ${fieldName(f)}`} onClick={()=>deleteField(f.id)}><X size={16}/></button>}
 </div>)}{!fields.length&&<p className="text-sm text-slate-500">ยังไม่มี Field — ใช้ Auto Layout หรือเพิ่มกรอบ Manual</p>}</div>;
 return <div className="page-stack" data-testid={`workflow-${stage}`}>
 <PageHeader title={stageTitles[stages.indexOf(stage)]} description={`${doc.filename} · ${doc.document_type_name||"ไม่ระบุประเภท"} · หน้า ${doc.page_number??1}`} actions={<Link href="/history" className="button secondary">ประวัติ</Link>}/>
 <WorkflowSteps stage={stage} saved={saved} uploadUrl={`/?document=${doc.id}${doc.document_type==="pdf"?`&page=${doc.page_number??1}`:""}`} busy={busy}/>
 {error&&<div className="error-banner" role="alert">{error}</div>}{busy&&<p role="status" className="notice-banner">กำลังดำเนินการ…</p>}{saveMessage&&<p role="status" className="notice-banner">{saveMessage}</p>}
 {!allowed?<section className="panel panel-body"><p>กรุณาทำขั้นตอนก่อนหน้าให้เสร็จก่อน</p><Link className="button primary" href={workflowUrl(saved.id,locked?"pipelines":"layout")}>กลับไปขั้นตอนก่อนหน้า</Link></section>:<>
 {stage==="ground-truth"&&comparison?<>
 {notice&&<p role="status" className="notice-banner">คำนวณแล้ว — ผลประเมินอยู่ในตาราง</p>}
 <GlobalFieldEvaluation fields={fields} saved={saved} runs={latestRuns} mode={mode} documentGT={documentGT} busy={busy} onMode={setMode} onEdit={()=>{setComparison(false);setNotice(false);}}/>
 </>:<div className="grid gap-5 lg:grid-cols-2">
 <section data-testid="preview-column" className="relative min-w-0 lg:min-h-[560px]"><div className="lg:absolute lg:inset-0">
 <DocumentViewer fillParent showGlobalFieldToggle={stage!=="pipelines"} onClearSelection={()=>{if(!busy)setActiveId(null);}} reviewMode={stage==="ground-truth"} imageUrl={api.assetUrl(doc.image_url)} width={doc.width} height={doc.height} roi={active?.roi??null} onRoiChange={edit} onManualRoi={r=>add(r,"manual")} globalFields={fields} selectedGlobalFieldId={activeId} showRoiDelete={false} onSelectGlobalField={selectPreviewField} boxes={[]} selectedBoxId={null} onSelectBox={()=>{}} regionMode={drawing} onRegionModeChange={setDrawing} allowRoi={stage==="layout"&&!locked&&!busy}/>
 </div></section><section data-testid="controls-column" className="min-w-0 space-y-4">
 {stage==="layout"&&<div className="panel panel-body space-y-4 lg:h-full"><h2>จัดการ Global Fields</h2>
 <div className="flex flex-wrap gap-2"><button className="button secondary" disabled={busy} onClick={()=>void act(async()=>{const regions=(await api.getAutoROIs(doc.id,"text-line",doc.page_number)).regions;setFields(old=>previewFieldOrder([...old,...regions.filter(r=>!old.some(f=>JSON.stringify(f.roi)===JSON.stringify(r.roi))).map(r=>({id:crypto.randomUUID(),field_index:0,roi:r.roi,source:"auto" as const,ground_truth_raw:null,confirmed_at:null}))]));})}>Auto Layout</button><button className="button secondary" disabled={busy} onClick={()=>setDrawing(true)}>เพิ่มกรอบ Manual</button></div>
 <p className="text-sm text-slate-600">Auto Layout ค้นหาข้อความและเพิ่มกรอบ ROI อัตโนมัติ · Manual ใช้ลากวาดกรอบเอง วาดต่อได้หลายกรอบจนกว่าจะเปลี่ยนเครื่องมือ</p>
 <p className="text-xs text-slate-500">เครื่องมือรูปมือใช้ลากเลื่อนภาพเมื่อซูมหรือภาพใหญ่กว่าพื้นที่พรีวิว โดยไม่แก้ไขกรอบ</p>
 {fieldList}
 <p className="text-xs text-slate-500">ทุก Field ในรายการจะถูกนำไปใช้ กด × ท้าย Field ที่ไม่ต้องการเพื่อนำออก</p>
 <p className="text-xs text-slate-500">{layoutDirty?"มีการแก้ไขที่ยังไม่ได้บันทึก · ":""}บันทึกฉบับร่างเพื่อแก้ต่อ หรือยืนยัน ROI เพื่อบันทึกและไปเลือก Pipeline ย้อนกลับมาแก้กรอบได้เสมอ</p>
 {hasRuns&&<p className="text-xs text-amber-800">หากแก้กรอบแล้วบันทึก จะสร้างชุดแก้ไขสำหรับรัน OCR ใหม่ โดยเก็บ GT ติดกับ Field เดิมแม้ลำดับเปลี่ยน กรอบใหม่เริ่มว่าง และผลประเมินเดิมยังอยู่ในประวัติ</p>}
 <div className="flex flex-wrap gap-2"><button className="button secondary" disabled={busy||!layoutDirty} onClick={()=>void act(async()=>{const c=await saveLayout(false);adopt(c);if(c.id!==saved.id)router.replace(workflowUrl(c.id,"layout"));setSaveMessage("บันทึก Layout ฉบับร่างแล้ว — ยังแก้ไขกรอบได้");})}>บันทึก Layout ฉบับร่าง</button><button className="button primary" disabled={busy||!fields.length} onClick={()=>void act(async()=>{const c=await saveLayout(true);adopt(c);router.push(workflowUrl(c.id,"pipelines"));})}>ยืนยัน ROI</button></div>
 </div>}
 {stage==="pipelines"&&<section className="panel panel-body space-y-4 lg:h-full"><h2>เลือก Pipelines</h2><p>ทุก Pipeline จะใช้ Global Field ชุดเดียวกัน</p><div data-testid="pipeline-options" aria-busy={busy} className={`space-y-3 transition-opacity ${busy?"opacity-50":"opacity-100"}`}>{configs.map(p=><label key={p.pipeline_id} className="flex gap-2"><input type="checkbox" aria-label={`เลือก ${pipelineLabel(p.pipeline_id,p.name)}`} disabled={busy||!p.enabled} checked={pipelineIds.includes(p.pipeline_id)} onChange={e=>setPipelineIds(old=>e.target.checked?[...old,p.pipeline_id]:old.filter(id=>id!==p.pipeline_id))}/>{pipelineLabel(p.pipeline_id,p.name)}{!p.enabled&&" (ปิดอยู่)"}</label>)}</div><button aria-busy={busy} className="button primary" disabled={busy||!pipelineIds.length} onClick={()=>void act(async()=>{await api.runPipelines(saved.id,pipelineIds);router.push(workflowUrl(saved.id,"ground-truth")+"?edit=1");})}>{busy?<><LoaderCircle aria-hidden="true" data-testid="ocr-spinner" className="h-4 w-4 animate-spin"/>กำลังรัน OCR...</>:"Run OCR"}</button></section>}
 {stage==="ground-truth"&&<GlobalGroundTruthForm mode={mode} fields={fields} documentGT={documentGT} lineCounts={lineCounts} onLineCounts={counts=>changeDocument(documentGT,counts)} busy={busy} onActivateField={selectField} onMode={m=>{setMode(m);setNotice(false);setSaveMessage("");}} onDocument={changeDocument} onField={changeField} onSave={calculate=>void saveGT(calculate)}/>}
 </section></div>}</>}
 </div>;
}
