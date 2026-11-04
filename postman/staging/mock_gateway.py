"""Synthetic leaf contract simulator. It never calls CDGS or reads real documents."""
import asyncio,json,time
from io import BytesIO
from uuid import uuid4
from fastapi import FastAPI,Request
from fastapi.responses import StreamingResponse
from PIL import Image

app=FastAPI();active=0;profile='sized';events=[]
# ~3.33 MB numeric JSON per REC input. Size-matched surrogate, not captured CDGS content.
numeric=b'['+b'0.1234567,'*333_000+b'0]'
@app.get('/diagnostics')
def diagnostics():return {'active':active,'events':events,'profile':profile}
@app.post('/diagnostics/profile/{value}')
def set_profile(value:str):
 global profile
 if value not in {'compact','sized'}:return {'error':'unsupported profile'}
 profile=value;return {'profile':profile}
@app.get('/paddle/api/v1/health')
@app.get('/paddle/api/v1/readiness')
def health():return {'data':{'status':'ok','services':[{'name':s,'status':'ready'} for s in ['text-detection','text-recognition']]},'meta':{}}
@app.post('/paddle/api/v1/{stage}')
async def infer(stage:str,request:Request):
 global active
 started=time.time();rid=request.headers.get('x-request-id',uuid4().hex)
 form=await request.form();files=form.getlist('images');dims=[]
 for file in files:
  data=await file.read()
  with Image.open(BytesIO(data)) as im:dims.append([im.width,im.height])
 det=stage=='text-detection-batches';active+=1
 e={'request_id':rid,'stage':'det' if det else 'rec','params':dict(request.query_params),'start':started,'active_on_start':active,'count':len(files),'dimensions':dims,'profile':profile}
 events.append(e)
 try:
  await asyncio.sleep(.15)
  rows=[{'dt_polys':[[[1,1],[w-2,1],[w-2,h-2],[1,h-2]]],'dt_scores':[.95]} if det else {'rec_text':'SYNTHETIC 123','rec_score':.95} for w,h in dims]
  selection={'kind':'detection' if det else 'recognition','version':'v'+request.query_params.get('version','6'),'variant':request.query_params.get('model','baseline'),'model_name':'SYNTHETIC_MOCK_ONLY'}
  data={'kind':'text_detection_batch' if det else 'text_recognition_batch','contract_version':'leaf-inference-v1','count':len(rows),'results':rows,'result':{'results':rows},'model_selection':selection}
  meta={'request_id':rid,'duration_ms':150,'service':'isolated-mock','model':'SYNTHETIC_MOCK_ONLY'}
  head=json.dumps({'data':data,'meta':meta},separators=(',',':')).encode()
  if det or profile=='compact':
   body=head;e.update(status=200,response_bytes=len(body))
   async def stream():yield body
  else:
   # Inject one numeric array per input without allocating a second giant mock response.
   prefix=head[:-1]+b',"synthetic_numeric_output":['
   size=len(prefix)+len(numeric)*len(rows)+max(0,len(rows)-1)+2
   e.update(status=200,response_bytes=size)
   async def stream():
    yield prefix
    for i in range(len(rows)):
     if i:yield b','
     for offset in range(0,len(numeric),65536):yield numeric[offset:offset+65536]
    yield b']}'
  async def observed_stream():
   global active
   try:
    async for chunk in stream():yield chunk
   finally:e['end']=time.time();active-=1
  return StreamingResponse(observed_stream(),media_type='application/json')
 finally:
  e['handler_end']=time.time()
