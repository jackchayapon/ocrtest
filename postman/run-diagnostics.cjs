/* Bounded Newman runner. Credentials live in memory; raw Newman summaries are never exported. */
const fs=require('fs');
const path=require('path');
const crypto=require('crypto');
const {spawnSync}=require('child_process');
const root=path.resolve(__dirname,'..');
const newman=require(path.join(root,'.runtime/cdgs-newman-tools/node_modules/newman'));
const mode=process.argv[2]||'baseline';
if(!['baseline','read','backend','single'].includes(mode)) throw new Error('Use baseline, read, backend or single');
const dir=path.join(root,'.runtime/cdgs-newman');fs.mkdirSync(dir,{recursive:true});
const coll=JSON.parse(fs.readFileSync(path.join(__dirname,'cdgs-diagnostics.postman_collection.json'),'utf8'));
const env=JSON.parse(fs.readFileSync(path.join(__dirname,'cdgs-diagnostics.postman_environment.json'),'utf8'));
const privateEnv=spawnSync(path.join(root,'backend/.venv/Scripts/python.exe'),['-c',"import json;from dotenv import dotenv_values;print(json.dumps({'key':dotenv_values('.env').get('MODEL_GATEWAY_API_KEY','')}))"],{cwd:root,encoding:'utf8'});
if(privateEnv.status!==0) throw new Error('Cannot read private environment');
const key=JSON.parse(privateEnv.stdout).key.trim();
if(!key)throw new Error('Private Gateway key missing');
function set(k,v){env.values.find(x=>x.key===k).value=v;}
set('gateway_api_key',key);set('field_id',crypto.randomUUID());
if(mode==='backend')set('allow_synthetic_writes','true');
coll.item=coll.item.filter(f=>f.name.startsWith('01') || (mode==='baseline'&&f.name.startsWith('02')) || (mode==='backend'&&f.name.startsWith('03')) || (mode==='single'&&f.name.startsWith('02')));
if(mode==='single'){
 coll.item=coll.item.filter(f=>f.name.startsWith('02'));
 coll.item[0].item=coll.item[0].item.filter(i=>i.name==='REC V5 thai_ft_v6');
}
for(const folder of coll.item)for(const item of folder.item||[])for(const part of item.request.body?.formdata||[])if(part.type==='file')part.src=path.join(__dirname,'synthetic.png');
const report={mode,started_at:new Date().toISOString(),concurrency:1,max_iterations:mode==='single'?3:1,requests:[],assertion_failures:[],stopped:false};
const starts=new Map();let runner;
function redact(x){return String(x??'').split(key).join('[REDACTED]').replace(/Bearer\s+\S+/gi,'Bearer [REDACTED]').replace(/data:image\/[^\s]+/g,'[IMAGE OMITTED]').slice(0,700);}
function stop(reason){report.stopped=true;report.stop_reason=reason;runner.abort();}
function save(){fs.writeFileSync(path.join(dir,'newman-'+mode+'.json'),JSON.stringify(report,null,2));}
runner=newman.run({collection:coll,environment:env,iterationCount:report.max_iterations,reporters:[],timeoutRequest:60000,timeoutScript:10000,ignoreRedirects:true,bail:false},(error,summary)=>{
 report.finished_at=new Date().toISOString();report.runner_error=error?error.name:null;
 report.stats=summary?.run?.stats;
 report.synthetic_ids=Object.fromEntries(['document_id','test_case_id','run_id'].map(k=>[k,summary?.environment?.get(k)||null]));
 save();console.log(JSON.stringify({mode,requests:report.requests.length,assertions:report.stats?.assertions,stopped:report.stopped,status_counts:report.requests.reduce((m,x)=>(m[x.status]=(m[x.status]||0)+1,m),{})}));
 if(error||report.stopped||report.assertion_failures.length)process.exitCode=1;
});
runner.on('beforeRequest',(_,a)=>starts.set(a.cursor.ref,new Date().toISOString()));
runner.on('assertion',(_,a)=>{if(a.error)report.assertion_failures.push({test:redact(a.assertion),name:a.error.name});});
runner.on('request',(error,a)=>{
 const item=a.item.name;
 if(error){report.requests.push({name:item,error:error.name});save();stop('connection_error');return;}
 const requestUrl=new URL(a.request.url.toString());
 const row={name:item,iteration:a.cursor.iteration,start:starts.get(a.cursor.ref),end:new Date().toISOString(),host:requestUrl.hostname,path:requestUrl.pathname,query:Object.fromEntries(requestUrl.searchParams),status:a.response.code,latency_ms:a.response.responseTime,response_bytes:a.response.stream?.length??null,request_id:a.request.headers.get('X-Request-ID')};
 let d;try{d=a.response.json();}catch{row.non_json=true;}
 if(requestUrl.hostname==='websolution.cdgs.co.th')row.input={count:1,dimensions:[1000,240],format:'image/png',sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(__dirname,'synthetic.png'))).digest('hex')};
 if(d?.meta)row.meta=Object.fromEntries(['request_id','duration_ms','service','model'].filter(k=>k in d.meta).map(k=>[k,d.meta[k]]));
 if(d?.data){row.data_keys=Object.keys(d.data);row.count=d.data.count;row.model_selection=d.data.model_selection;}
 if(d?.error){row.error=Object.fromEntries(['code','message','request_id'].filter(k=>k in d.error).map(k=>[k,redact(d.error[k])]));
  if(Array.isArray(d.error.details))row.error.details=d.error.details.slice(0,5).map(x=>Object.fromEntries(['code','message','type','loc','msg'].filter(k=>k in x).map(k=>[k,redact(x[k])])));}
 if(Array.isArray(d?.runs))row.runs=d.runs.map(r=>({id:r.id,pipeline_id:r.pipeline_id,status:r.status,error_code:r.error_code,fields:(r.fields||[]).map(f=>({status:f.status,request_id:f.diagnostics?.request_id,gateway_request_id:f.diagnostics?.gateway_request_id,error_code:f.diagnostics?.error_code,crop_width:f.diagnostics?.crop_width,crop_height:f.diagnostics?.crop_height}))}));
 report.requests.push(row);save();
 if(item==='Pipeline catalog'&&Array.isArray(d)){
  const p=d.find(p=>p.enabled&&p.source==='custom'&&p.execution_mode==='det_rec'&&p.det_model?.version==='6'&&p.det_model?.weight==='baseline'&&p.rec_model?.version==='5'&&p.rec_model?.weight==='baseline');
  if(mode==='backend'&&!p){stop('no_enabled_baseline_pipeline');return;}
 }
 if(a.response.code>=500||a.response.code===429||(mode==='backend'&&a.response.code>=400))stop('unsafe_http_status_'+a.response.code);
});
