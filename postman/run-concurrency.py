"""Bounded staging-only dispatch: B=2x3, C=4x2. Never targets production."""
import argparse,asyncio,json,os,time,re
from uuid import UUID
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
import httpx

parser=argparse.ArgumentParser()
parser.add_argument('--level',choices=['B','C'],required=True)
args=parser.parse_args()
base=os.environ.get('STAGING_BACKEND_BASE_URL','').rstrip('/')
case=os.environ.get('STAGING_SYNTHETIC_CASE_ID','')
pipeline=os.environ.get('STAGING_PIPELINE_ID','')
parts=urlsplit(base)
if (os.environ.get('ALLOW_STAGING_CONCURRENCY')!='true' or not parts.hostname
    or parts.scheme!='https' or parts.username or parts.password or parts.query or parts.fragment
    or parts.hostname in {'ocrtest-production-095b.up.railway.app','ocrtest-sandy.vercel.app','websolution.cdgs.co.th'}
    or not case or not pipeline):
 raise SystemExit('BLOCKED: explicit isolated staging URL, synthetic case/pipeline and opt-in required')
try:UUID(case)
except ValueError:raise SystemExit('BLOCKED: invalid staging case UUID')
if not re.fullmatch(r'[a-z][a-z0-9_]{0,49}',pipeline):raise SystemExit('BLOCKED: invalid pipeline ID')
concurrency,trials=(2,3) if args.level=='B' else (4,2)
report={'level':args.level,'concurrency':concurrency,'max_trials':trials,'requests':[],'stopped':False}
def stamp():return datetime.now(timezone.utc).isoformat()
def save():
 out=Path('.runtime/cdgs-newman');out.mkdir(parents=True,exist_ok=True)
 (out/('concurrency-'+args.level+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
async def main():
 async with httpx.AsyncClient(timeout=60,follow_redirects=False,limits=httpx.Limits(max_connections=4)) as client:
  r=await client.get(base+'/api/test-cases/'+case)
  if r.status_code!=200:raise SystemExit('BLOCKED: staging case cannot be verified')
  d=r.json()
  if (not d.get('document',{}).get('filename','').startswith('CDGS_DIAGNOSTIC_')
      or d.get('workflow')!='global' or len(d.get('global_fields',[]))!=1
      or not d['global_fields'][0].get('ground_truth_raw')):
   raise SystemExit('BLOCKED: requires one synthetic field with manual GT to avoid prefill')
  async def send(trial,index):
   item={'trial':trial,'index':index,'start':stamp()};start=time.perf_counter()
   try:
    r=await client.post(base+'/api/test-cases/'+case+'/run',json={'pipelines':[pipeline]},headers={'X-Request-ID':f'diag-staging-{args.level}-{trial}-{index}'})
    item.update(status=r.status_code,response_bytes=len(r.content))
    try:item['run_statuses']=[x.get('status') for x in r.json().get('runs',[])]
    except (ValueError,AttributeError):pass
    if r.status_code>=500 or r.status_code==429:report['stopped']=True
   except httpx.RequestError as exc:item['error']=type(exc).__name__;report['stopped']=True
   finally:item.update(end=stamp(),latency_ms=round((time.perf_counter()-start)*1000,2));report['requests'].append(item);save()
  for trial in range(1,trials+1):
   await asyncio.gather(*(send(trial,i) for i in range(1,concurrency+1)))
   if report['stopped']:break
 save();print(json.dumps({'requests':len(report['requests']),'stopped':report['stopped']}))
asyncio.run(main())
