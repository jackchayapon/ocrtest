"""Local/staging-only process observer; original app files remain unchanged."""
import asyncio,gc,json,os,resource,threading,time
from io import BytesIO
from pathlib import Path
from PIL import Image
import uvicorn

output=Path('/evidence');output.mkdir(exist_ok=True)
log=output/'process.jsonl';lock=threading.Lock();active=0
def usage():
 result={'time':time.time(),'pid':os.getpid()}
 try:
  status=Path('/proc/self/status').read_text().splitlines()
  result.update({x.split(':')[0]:int(x.split()[1])*1024 for x in status if x.startswith(('VmRSS:','VmHWM:'))})
  result['cgroup_current']=int(Path('/sys/fs/cgroup/memory.current').read_text())
  stats=dict(line.split() for line in Path('/sys/fs/cgroup/memory.stat').read_text().splitlines())
  result['cgroup_inactive_file']=int(stats.get('inactive_file',0))
  result['cgroup_anon']=int(stats.get('anon',0))
  result['cgroup_working_set']=max(0,result['cgroup_current']-result['cgroup_inactive_file'])
  result['cgroup_max']=Path('/sys/fs/cgroup/memory.max').read_text().strip()
  result['cgroup_events']=Path('/sys/fs/cgroup/memory.events').read_text().strip()
 except (OSError,ValueError):pass
 r=resource.getrusage(resource.RUSAGE_SELF);result.update(cpu_user=r.ru_utime,cpu_system=r.ru_stime)
 return result
def emit(event,**extra):
 with lock:
  with log.open('a') as f:f.write(json.dumps({'event':event,**usage(),**extra})+'\n')
def sampler():
 while True:emit('sample',active_gateway_tasks=active);time.sleep(.05)
threading.Thread(target=sampler,daemon=True).start()
from app.integrations.model_gateway import ModelGatewayClient
original_send=ModelGatewayClient.send
async def send(self,request):
 global active
 active+=1;rid=request['headers'].get('X-Request-ID');dims=[]
 for _,part in request.get('files',[]):
  with Image.open(BytesIO(part[1])) as image:dims.append([image.width,image.height])
 emit('gateway_start',request_id=rid,params=request.get('params'),input_count=len(dims),dimensions=dims,active_gateway_tasks=active)
 try:return await original_send(self,request)
 finally:active-=1;emit('gateway_end',request_id=rid,active_gateway_tasks=active)
ModelGatewayClient.send=send
from app.services.pipeline_manager import PipelineManager
from app.pipelines.dynamic import DynamicDetectionRecognitionAdapter
active_fields=0;active_pipelines=0;active_http=0
original_manager_run=PipelineManager.run
async def manager_run(self,*a,**kw):
 global active_fields
 active_fields+=1;emit('field_task_start',active_fields=active_fields)
 try:return await original_manager_run(self,*a,**kw)
 finally:active_fields-=1;emit('field_task_end',active_fields=active_fields)
PipelineManager.run=manager_run
original_adapter_run=DynamicDetectionRecognitionAdapter.run
async def adapter_run(self,*a,**kw):
 global active_pipelines
 active_pipelines+=1;emit('pipeline_task_start',active_pipelines=active_pipelines,pipeline_id=self.config.pipeline_id)
 try:return await original_adapter_run(self,*a,**kw)
 finally:active_pipelines-=1;emit('pipeline_task_end',active_pipelines=active_pipelines)
DynamicDetectionRecognitionAdapter.run=adapter_run
original_loads=json.loads
def loads(value,*a,**kw):
 large=isinstance(value,(bytes,bytearray,str)) and len(value)>1_000_000
 if large:emit('json_decode_start',response_bytes=len(value))
 try:return original_loads(value,*a,**kw)
 finally:
  if large:emit('json_decode_end',response_bytes=len(value))
json.loads=loads
def gc_event(phase,info):
 if info.get('generation')==2:emit('gc_'+phase,generation=2)
gc.callbacks.append(gc_event)
emit('observer_ready',note='Synthetic diagnostics only; no credentials/bodies logged')
from app.main import app as original_app
class ObservedHTTP:
 async def __call__(self,scope,receive,send):
  global active_http
  watched=scope['type']=='http' and scope.get('path','').endswith('/run')
  if watched:active_http+=1;emit('http_run_start',active_http=active_http)
  try:await original_app(scope,receive,send)
  finally:
   if watched:active_http-=1;emit('http_run_end',active_http=active_http)
uvicorn.run(ObservedHTTP(),host='0.0.0.0',port=8000,access_log=False)
