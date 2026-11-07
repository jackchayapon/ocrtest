"""Local PostgreSQL + 512 MB/one CPU only; never calls real CDGS.

Run after isolated compose setup. --recover kills ONLY the named local container
after its first persisted checkpoint. Completed unit IDs must survive unchanged.
"""
import asyncio
import importlib.util
import json
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import httpx
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/(".runtime/audit" if "--audit" in sys.argv else ".runtime/jobs")
spec=importlib.util.spec_from_file_location("diagnostics",Path(__file__).with_name("concurrency-test.py"))
diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(diag)
diag.CONTAINER="ocrlab-jobs-backend-1";diag.EVIDENCE=ROOT/".runtime/jobs/evidence"
BASE,MOCK=diag.BASE,diag.MOCK


async def main(recover=False,no_browser=False):
    field_count,pipeline_count=(38,13) if "--audit" in sys.argv else (40,12)
    total=field_count*pipeline_count
    row={"scope":"LOCAL ISOLATED MOCK ONLY", "fields":field_count,"pipelines":pipeline_count,"expected_outputs":total,"recovery":recover}
    async with httpx.AsyncClient(timeout=30,follow_redirects=False,trust_env=False) as c:
        for attempt in range(30):
            try:
                response=await c.get(BASE+"/api/health")
                if response.status_code==200:break
            except httpx.RequestError:pass
            await asyncio.sleep(1)
        else:raise RuntimeError("Isolated backend did not become ready")
        await diag.models_and_pipelines(c)
        models=await diag.checked(c,"GET","/api/pipelines/models")
        def model(kind,version,weight):
            return next(m["id"] for m in models if m["source"]=="custom" and m["kind"]==kind and m["version"]==version and m["weight"]==weight)
        recognition=[("5",w) for w in ("baseline","thai_ft_v3","thai_ft_v4","thai_ft_v6")]+[("6","thai_ft_v1")]
        specs=[("det_rec",d,v,r) for d in ("baseline","thai_ft_v2") for v,r in recognition]+[("rec",None,"5","baseline"),("rec",None,"6","thai_ft_v1")]
        if pipeline_count==13:
            specs.append(("rec",None,"5","thai_ft_v6"))
        pipelines=[]
        for mode,det,v,r in specs:
            p=await diag.checked(c,"POST","/api/pipelines",json={"name":"SYNTHETIC JOB "+uuid4().hex[:6],"source":"custom","execution_mode":mode,"enabled":True,"det_model_id":model("det","6",det) if det else None,"rec_model_id":model("rec",v,r)})
            pipelines.append(p["pipeline_id"])
        image=Image.new("RGB",(4000,3200),"white");draw=ImageDraw.Draw(image);fields=[]
        for i in range(field_count):
            x,y=(i%5)*800,(i//5)*400
            draw.rectangle((x,y,x+799,y+399),fill=(i+1,120,200))
            fields.append({"id":str(uuid4()),"field_index":i+1,"source":"manual","roi":{"x1":x,"y1":y,"x2":x+800,"y2":y+400},"ground_truth_raw":f"SYNTHETIC {i+1:02d}"})
        buf=BytesIO();image.save(buf,format="PNG");image.close()
        doc=await diag.checked(c,"POST","/api/documents",files={"file":("synthetic-job.png",buf.getvalue(),"image/png")})
        case=await diag.checked(c,"POST","/api/test-cases",json={"document_id":doc["id"],"workflow":"global","ground_truth_raw":"synthetic GT disables assistance"})
        cid=case["id"];row["case_id"]=cid
        await diag.checked(c,"PUT",f"/api/test-cases/{cid}/global-fields",json={"fields":fields,"confirmed":True})
        await c.post(MOCK+"/diagnostics/profile/sized");await c.post(MOCK+"/diagnostics/identity/true")
        await c.post(MOCK+"/diagnostics/delay/3")
        offset=len((await c.get(MOCK+"/diagnostics")).json()["events"])
        started=time.time();job=await diag.checked(c,"POST",f"/api/test-cases/{cid}/jobs",json={"pipelines":pipelines,"idempotency_key":str(uuid4())})
        row.update(job_id=job["job_id"],creation_ms=round((time.time()-started)*1000,2))
    # Creation HTTP connection is closed; subsequent clients only read progress.
    row["no_browser_seconds"]=0
    if no_browser:
        observations=[]
        for _ in range(11):
            await asyncio.sleep(30)
            # This connects directly to the local DB; no HTTP to the backend.
            jid=str(__import__('uuid').UUID(job['job_id']))
            q="SELECT status,completed_units,heartbeat_at,attempt_count FROM ocr_jobs WHERE id='"+jid+"'"
            result=subprocess.run(['docker','exec','ocrlab-jobs-db-1','psql','-U','diagnostics','-d','diagnostics','-At','-c',q],capture_output=True,text=True,check=True)
            observations.append({"elapsed":round(time.time()-started,2),"db_state":result.stdout.strip()})
        row["no_browser_seconds"]=330
        row["independent_db_observations"]=observations
    progress=[];preserved=set();killed=False;poll_bytes=0;poll_times=[]
    while time.time()-started<1000:
        await asyncio.sleep(3)
        try:
            async with httpx.AsyncClient(timeout=10,trust_env=False) as c:
                poll_started=time.perf_counter()
                response=await c.get(BASE+f"/api/ocr-jobs/{job['job_id']}")
                response.raise_for_status();job=response.json()
                poll_bytes+=len(response.content);poll_times.append(round((time.perf_counter()-poll_started)*1000,2))
                progress.append({"elapsed":round(time.time()-started,2),"completed":job["completed_units"],"status":job["status"],"attempts":job["attempt_count"]})
                if recover and not killed and job["completed_units"]>=96 and job["status"]=="running":
                    saved=await diag.checked(c,"GET",f"/api/ocr-jobs/{job['job_id']}/results")
                    preserved={f["id"] for r in saved["runs"] for f in r["fields"]}
                    subprocess.run(["docker","kill",diag.CONTAINER],check=True,capture_output=True)
                    await asyncio.sleep(2)
                    subprocess.run(["docker","start",diag.CONTAINER],check=True,capture_output=True)
                    row["killed_after_units"]=len(preserved);row["kill_elapsed"]=round(time.time()-started,2);killed=True
                if job["status"] not in ("queued","running"):
                    break
        except httpx.RequestError:
            continue
    async with httpx.AsyncClient(timeout=30,trust_env=False) as c:
        saved=await diag.checked(c,"GET",f"/api/ocr-jobs/{job['job_id']}/results")
        all_ids=[];correct=0;traces=0;confidences=0;geometry=0
        for run,(_,_,v,r) in zip(saved["runs"],specs):
            assert len(run["fields"])==field_count
            for i,f in enumerate(run["fields"]):
                all_ids.append(f["id"])
                correct+=f["ocr_text"]==f"SYNTHETIC {i+1:02d} v{v} {r}" and f["global_field_id"]==fields[i]["id"] and f["status"]=="success"
                traces+=bool(f["diagnostics"].get("request_id") and f["diagnostics"].get("gateway_request_id"))
                confidences+=f["confidence"]==.95
                geometry+=bool(f["diagnostics"].get("boxes"))
        events=(await c.get(MOCK+"/diagnostics")).json()["events"][offset:]
        await c.post(MOCK+"/diagnostics/delay/0.15")
    row.update(final_job=job,elapsed_seconds=round(time.time()-started,2),correct=correct,persisted=len(all_ids),unique=len(set(all_ids)),preserved_checkpoint_ids=len(preserved.intersection(all_ids)),confidence=confidences,traces=traces,geometry=geometry,gateway_calls=len(events),progress=progress,resources=diag.summarize(started,time.time()),container=diag.inspect())
    row.update(poll_count=len(poll_times),poll_response_bytes=poll_bytes,poll_latency_ms=poll_times,
               database_transactions=sum(s["event"]=="db_transaction" for s in diag.samples(started,time.time())))
    row["pass"]=job["status"]=="completed" and correct==total and confidences==total and traces==total and geometry==10*field_count and len(set(all_ids))==total and len(preserved.intersection(all_ids))==len(preserved) and row["elapsed_seconds"]>300 and not row["container"]["state"]["OOMKilled"] and all(a["completed"]<=b["completed"] for a,b in zip(progress,progress[1:]))
    (OUT/("scale-no-browser.json" if no_browser else "scale-recovery.json" if recover else "scale.json")).write_text(json.dumps(row,indent=2),encoding="utf-8")
    print(json.dumps({k:row[k] for k in ("pass","creation_ms","elapsed_seconds","correct","unique","gateway_calls")}))


if __name__=="__main__":
    asyncio.run(main("--recover" in sys.argv,"--no-browser" in sys.argv))
