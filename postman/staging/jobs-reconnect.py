"""Local-only outage test. Stops/restarts ONLY ocrlab-jobs-db-1.

Requires the isolated jobs compose project; never uses production settings/key.
"""
import asyncio
import json
import subprocess
import time
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import httpx
from PIL import Image

BASE="http://127.0.0.1:18080"
MOCK="http://127.0.0.1:18081"
OUT=Path(__file__).resolve().parents[2]/".runtime/jobs/database-reconnect.json"


async def main():
    async with httpx.AsyncClient(timeout=15,trust_env=False) as c:
        async def call(method,path,**kwargs):
            r=await c.request(method,BASE+path,**kwargs)
            r.raise_for_status()
            return r.json()
        for _ in range(30):
            try:
                if (await c.get(BASE+"/api/health")).status_code==200:break
            except httpx.HTTPError:pass
            await asyncio.sleep(1)
        models=await call("GET","/api/pipelines/models")
        model=next(m for m in models if m["kind"]=="rec" and m["version"]=="5" and m["weight"]=="baseline" and m["source"]=="custom")
        pipeline=await call("POST","/api/pipelines",json={"name":"SYNTHETIC DATABASE RECOVERY "+uuid4().hex[:6],"source":"custom","execution_mode":"rec","rec_model_id":model["id"],"enabled":True})
        image=Image.new("RGB",(1000,1000),(42,120,200));buf=BytesIO();image.save(buf,format="PNG");image.close()
        doc=await call("POST","/api/documents",files={"file":("synthetic-reconnect.png",buf.getvalue(),"image/png")})
        case=await call("POST","/api/test-cases",json={"document_id":doc["id"],"workflow":"global","ground_truth_raw":"synthetic GT; no assistance"})
        fields=[{"id":str(uuid4()),"field_index":i+1,"source":"manual","roi":{"x1":i%5*200,"y1":i//5*125,"x2":i%5*200+200,"y2":i//5*125+125},"ground_truth_raw":"SYNTHETIC"} for i in range(40)]
        await call("PUT",f"/api/test-cases/{case['id']}/global-fields",json={"fields":fields,"confirmed":True})
        await c.post(MOCK+"/diagnostics/profile/sized");await c.post(MOCK+"/diagnostics/delay/3")
        started=time.time()
        job=await call("POST",f"/api/test-cases/{case['id']}/jobs",json={"pipelines":[pipeline["pipeline_id"]],"idempotency_key":str(uuid4())})
        while True:
            await asyncio.sleep(.5)
            job=await call("GET",f"/api/ocr-jobs/{job['job_id']}")
            if job["completed_units"]>=8:break
            assert job["status"] in ("queued","running")
        saved=await call("GET",f"/api/ocr-jobs/{job['job_id']}/results")
        preserved={f["id"] for r in saved["runs"] for f in r["fields"]}
        check=subprocess.run(["docker","inspect","ocrlab-jobs-db-1"],capture_output=True,text=True,check=True)
        assert json.loads(check.stdout)[0]["Config"]["Labels"]["com.docker.compose.project"]=="ocrlab-jobs"
        subprocess.run(["docker","stop","--time","2","ocrlab-jobs-db-1"],check=True,capture_output=True)
        try:
            await asyncio.sleep(12)
            unavailable=await c.get(BASE+f"/api/ocr-jobs/{job['job_id']}",headers={"Origin":"http://127.0.0.1:3100"})
            assert unavailable.status_code==503
            assert unavailable.headers.get("access-control-allow-origin")=="http://127.0.0.1:3100"
            await asyncio.sleep(8)
        finally:
            subprocess.run(["docker","start","ocrlab-jobs-db-1"],check=True,capture_output=True)
        history=[]
        while time.time()-started<240:
            await asyncio.sleep(2)
            try:job=await call("GET",f"/api/ocr-jobs/{job['job_id']}")
            except httpx.HTTPError:continue
            history.append({"completed":job["completed_units"],"attempts":job["attempt_count"],"elapsed":round(time.time()-started,2)})
            if job["status"] not in ("queued","running"):break
        saved=await call("GET",f"/api/ocr-jobs/{job['job_id']}/results")
        ids=[f["id"] for r in saved["runs"] for f in r["fields"]]
        report={"scope":"LOCAL POSTGRESQL OUTAGE ONLY", "job":job,"outage_seconds":20,"elapsed_seconds":round(time.time()-started,2),"persisted":len(ids),"unique":len(set(ids)),"preserved_checkpoint_ids":len(preserved.intersection(ids)),"checkpoint_ids_before":len(preserved),"status_during_outage":unavailable.status_code,"cors_on_503":True,"progress":history}
        report["pass"]=job["status"]=="completed" and job["attempt_count"]>=2 and len(set(ids))==40 and preserved.issubset(ids)
        OUT.write_text(json.dumps(report,indent=2),encoding="utf-8")
        await c.post(MOCK+"/diagnostics/delay/0.15")
        print(json.dumps({k:report[k] for k in ("pass","persisted","unique","preserved_checkpoint_ids","elapsed_seconds")}))


if __name__=="__main__":asyncio.run(main())
