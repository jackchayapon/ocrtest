"""A–G bounded synthetic diagnostics against the isolated local deployment only."""
import asyncio,hashlib,json,math,subprocess,time,sys
from datetime import datetime,timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import httpx
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'.runtime/staging-diagnostics';EVIDENCE=OUT/'evidence'
MATRIX=json.loads((ROOT/'postman/staging/test-matrix.json').read_text())
BASE='http://127.0.0.1:18080';MOCK='http://127.0.0.1:18081'
CONTAINER='ocrlab-isolated-diagnostics-backend-1'
RESULT={'environment':'LOCAL ISOLATED DOCKER — MOCK GATEWAY','source_commit':MATRIX['source_commit'],'staging_url':BASE,'railway_staging_deployment':None,'stages':[],'gateway_only':[],'stopped':False}
OUTPUT=ROOT/'postman/staging/results.json'
if __name__=='__main__' and sys.argv[1:]:
 if sys.argv[1:]!=['--after']:raise SystemExit('Use no arguments for baseline or --after for recovery candidate')
 CONTAINER='ocrlab-recovery-after-backend-1';EVIDENCE=ROOT/'.runtime/recovery/evidence'
 OUTPUT=ROOT/'postman/staging/results-final.json'
 RESULT['source_commit']='recovery working-tree candidate; verify source_tree_sha256'
 digest=hashlib.sha256()
 for p in sorted((ROOT/'backend/app').rglob('*.py')):
  digest.update(p.relative_to(ROOT/'backend/app').as_posix().encode());digest.update(p.read_bytes())
 RESULT['source_tree_sha256']=digest.hexdigest()
def stamp():return datetime.now(timezone.utc).isoformat()
def save():
 OUTPUT.write_text(json.dumps(RESULT,indent=2),encoding='utf-8')
def inspect():
 p=subprocess.run(['docker','inspect',CONTAINER],capture_output=True,text=True,encoding='utf-8',check=True)
 d=json.loads(p.stdout)[0]
 return {'id':d['Id'],'state':{k:d['State'].get(k) for k in ['Status','Running','OOMKilled','ExitCode','Pid','StartedAt','FinishedAt']},'restart_count':d['RestartCount'],'memory_limit':d['HostConfig']['Memory'],'nano_cpus':d['HostConfig']['NanoCpus']}
def samples(start,end):
 rows=[]
 with (EVIDENCE/'process.jsonl').open() as f:
  for line in f:
   try:d=json.loads(line)
   except ValueError:continue
   if start<=d.get('time',0)<=end:rows.append(d)
 return rows
def summarize(start,end):
 rows=samples(start,end)
 starts=[x for x in rows if x['event']=='gateway_start']
 return {'sample_count':len(rows),'peak_rss_bytes':max((x.get('VmRSS',0) for x in rows),default=0),'peak_cgroup_bytes':max((x.get('cgroup_current',0) for x in rows),default=0),'max_gateway_inflight':max((x.get('active_gateway_tasks',0) for x in rows),default=0),'pids':sorted(set(x['pid'] for x in rows)),
  'cpu_user_seconds':max((x['cpu_user'] for x in rows),default=0)-min((x['cpu_user'] for x in rows),default=0),
  'cpu_system_seconds':max((x['cpu_system'] for x in rows),default=0)-min((x['cpu_system'] for x in rows),default=0),
  'gateway_dispatches':[{'request_id':x['request_id'],'params':x['params'],'count':x['input_count'],'dimensions':x['dimensions'],'time':x['time']} for x in starts],
  'json_decode_phases':[{k:x.get(k) for k in ['event','time','response_bytes','VmRSS','cgroup_current']} for x in rows if x['event'].startswith('json_decode_')],
  'cgroup_events_last':rows[-1].get('cgroup_events') if rows else None}
async def checked(client,method,path,**kw):
 r=await client.request(method,BASE+path,**kw)
 if r.status_code>=400:raise RuntimeError('Setup HTTP '+str(r.status_code)+' '+path.split('?')[0])
 return r.json()
async def models_and_pipelines(client):
 models=await checked(client,'GET','/api/pipelines/models?fresh=true')
 model_ids={}
 for kind,version,weight in [('det','6','baseline'),('det','6','thai_ft_v2'),('rec','5','baseline'),('rec','5','thai_ft_v3'),('rec','5','thai_ft_v4'),('rec','5','thai_ft_v6'),('rec','6','thai_ft_v1')]:
  m=next((m for m in models if m['source']=='custom' and m['kind']==kind and m['version']==version and m['weight']==weight),None)
  if m is None:
   stem='text-detection' if kind=='det' else 'text-recognition'
   m=await checked(client,'POST','/api/pipelines/models',json={'name':f'SYNTHETIC {kind} {version} {weight}','kind':kind,'version':version,'weight':weight,'source':'custom','batch_path':f'/api/v1/{stem}-batches?version={version}&model={weight}'})
  model_ids[(kind,version,weight)]=m['id']
 combos=[('baseline','5','baseline'),('baseline','5','thai_ft_v3'),('thai_ft_v2','5','thai_ft_v4'),('baseline','6','thai_ft_v1')]
 pipelines=[]
 for i,(det,ver,rec) in enumerate(combos):
  p=await checked(client,'POST','/api/pipelines',json={'name':f'SYNTHETIC_STAGING_{i+1}','source':'custom','execution_mode':'det_rec','enabled':True,'det_model_id':model_ids[('det','6',det)],'rec_model_id':model_ids[('rec',ver,rec)]})
  pipelines.append(p['pipeline_id'])
 return pipelines
def image(dataset):
 spec=next(x for x in MATRIX['datasets'] if x['name']==dataset)
 im=Image.new('RGB',(spec['width'],spec['height']),'white');ImageDraw.Draw(im).text((30,30),'SYNTHETIC OCR 123',fill='black');out=BytesIO();im.save(out,format='PNG');data=out.getvalue()
 (OUT/(dataset+'.png')).write_bytes(data)
 return data,spec
async def case(client,profile,stage):
 png,spec=image(stage['dataset'])
 doc=await checked(client,'POST','/api/documents',files={'file':(f'CDGS_DIAGNOSTIC_{profile}_{stage["stage"]}.png',png,'image/png')})
 record=await checked(client,'POST','/api/test-cases',json={'document_id':doc['id'],'workflow':'global','ground_truth_raw':'SYNTHETIC 123'})
 fields=[]
 count=stage['fields'];width=spec['width']//(2 if count==4 else 1);height=spec['height']//(2 if count>=2 else 1)
 for i in range(count):
  x=(i%2)*width if count==4 else 0;y=(i//2)*height if count==4 else i*height
  fields.append({'id':str(uuid4()),'field_index':i+1,'source':'manual','roi':{'x1':x,'y1':y,'x2':x+width,'y2':y+height},'ground_truth_raw':'SYNTHETIC 123'})
 await checked(client,'PUT',f'/api/test-cases/{record["id"]}/global-fields',json={'fields':fields,'confirmed':True})
 return record['id'],{'dimensions':[spec['width'],spec['height']],'sha256':hashlib.sha256(png).hexdigest()}
async def main():
 RESULT['started_at']=stamp();RESULT['initial_container']=inspect();save()
 async with httpx.AsyncClient(timeout=90,follow_redirects=False,trust_env=False,limits=httpx.Limits(max_connections=4)) as client:
  health=await checked(client,'GET','/api/health');assert health['database']['status']=='connected'
  pipelines=await models_and_pipelines(client);RESULT['synthetic_pipeline_ids']=pipelines
  # Gateway-only checks verify the simulator contract, never real CDGS availability.
  png,_=image('small')
  for kind,version,variant in [('det','6','baseline'),('det','6','thai_ft_v2'),('rec','5','baseline'),('rec','5','thai_ft_v3'),('rec','5','thai_ft_v4'),('rec','5','thai_ft_v6'),('rec','6','thai_ft_v1')]:
   path='text-detection-batches' if kind=='det' else 'text-recognition-batches'
   r=await client.post(MOCK+'/paddle/api/v1/'+path,params={'version':version,'model':variant},files=[('images',('synthetic.png',png,'image/png'))])
   RESULT['gateway_only'].append({'kind':kind,'version':version,'model':variant,'status':r.status_code,'response_bytes':len(r.content)});save()
   if r.status_code>=400:raise RuntimeError('Mock baseline failed')
  for profile in MATRIX['profiles']:
   await client.post(MOCK+'/diagnostics/profile/'+profile)
   for stage in MATRIX['stages']:
    ids=[];assets=[]
    for _ in range(stage['http_concurrency']):
     cid,asset=await case(client,profile,stage);ids.append(cid);assets.append(asset)
    before=(await client.get(MOCK+'/diagnostics')).json()['events'];offset=len(before)
    entry={'profile':profile,**stage,'test_case_ids':ids,'assets':assets,'started_at':stamp(),'start_epoch':time.time(),'http':[],'container_before':inspect()}
    RESULT['stages'].append(entry);save()
    async def run(cid):
     start=time.time();row={'test_case_id':cid,'start':start}
     try:
      r=await client.post(BASE+f'/api/test-cases/{cid}/run',json={'pipelines':pipelines[:stage['pipelines']]})
      row.update(status=r.status_code,response_bytes=len(r.content))
      if r.status_code==200:
       d=r.json();row['runs']=[{'id':r['id'],'pipeline_id':r['pipeline_id'],'status':r['status'],'error_code':r.get('error_code'),'fields':[{'status':f['status'],'gateway_request_id':f.get('diagnostics',{}).get('gateway_request_id'),'error_code':f.get('diagnostics',{}).get('error_code')} for f in r.get('fields',[])]} for r in d['runs']]
     except httpx.RequestError as exc:row['error']=type(exc).__name__
     row.update(end=time.time(),duration_ms=round((time.time()-start)*1000,2));entry['http'].append(row);save()
    await asyncio.gather(*(run(cid) for cid in ids))
    end=time.time();entry['end_epoch']=end;entry['finished_at']=stamp();entry['container_after']=inspect();entry['resources']=summarize(entry['start_epoch'],end)
    entry['gateway_events']=(await client.get(MOCK+'/diagnostics')).json()['events'][offset:]
    entry['gateway_calls']=len(entry['gateway_events']);entry['batch_image_counts']=[x['count'] for x in entry['gateway_events']]
    entry['gateway_response_bytes']=sum(x.get('response_bytes',0) for x in entry['gateway_events'])
    lat=sorted(x['duration_ms'] for x in entry['http']);entry['p95_ms']=lat[math.ceil(.95*len(lat))-1]
    entry['success']=sum(x.get('status')==200 and all(r['status']=='success' and all(f['status']=='success' for f in r['fields']) for r in x.get('runs',[])) for x in entry['http'])
    entry['http_422']=sum(x.get('status')==422 for x in entry['http']);entry['http_502']=sum(x.get('status')==502 for x in entry['http'])
    abnormal=entry['success']!=stage['http_concurrency'] or not entry['container_after']['state']['Running'] or entry['container_after']['state']['OOMKilled']
    print(json.dumps({'profile':profile,'stage':stage['stage'],'success':entry['success'],'http_502':entry['http_502'],'peak_rss_bytes':entry['resources']['peak_rss_bytes'],'peak_cgroup_bytes':entry['resources']['peak_cgroup_bytes'],'max_gateway_inflight':entry['resources']['max_gateway_inflight'],'calls':entry['gateway_calls'],'stopped':abnormal}),flush=True)
    if abnormal:RESULT['stopped']=True;RESULT['stop_stage']=profile+'/'+stage['stage'];save();return
    save()
 RESULT['finished_at']=stamp();save()
if __name__=='__main__':
 try:asyncio.run(main())
 except Exception as exc:
  RESULT['stopped']=True;RESULT['harness_error']=type(exc).__name__;save();print(json.dumps({'harness_error':type(exc).__name__}));raise SystemExit(1)
