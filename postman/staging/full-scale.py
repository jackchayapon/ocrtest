"""Local-only 30x12 API acceptance. Synthetic pixels prove field/model ownership."""
import asyncio
import hashlib
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

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("diagnostics", Path(__file__).with_name("concurrency-test.py"))
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)
diag.CONTAINER = "ocrlab-recovery-after-backend-1"
diag.EVIDENCE = ROOT / ".runtime/recovery/evidence"
OUT = ROOT / "postman/staging/full-scale-results.json"
BASE, MOCK = diag.BASE, diag.MOCK


async def main(label, repetitions, failure=False):
    if not BASE.startswith("http://127.0.0.1:") or not MOCK.startswith("http://127.0.0.1:"):
        raise RuntimeError("This harness is local-only")
    report = json.loads(OUT.read_text()) if OUT.exists() else {"scope": "LOCAL ISOLATED; SIZE-MATCHED MOCK, NOT CDGS LOAD", "runs": []}
    async with httpx.AsyncClient(timeout=900, follow_redirects=False, trust_env=False) as client:
        await diag.checked(client, "GET", "/api/health")
        await diag.models_and_pipelines(client)
        models = await diag.checked(client, "GET", "/api/pipelines/models")
        def model(kind, version, weight):
            return next(m for m in models if m["source"] == "custom" and m["kind"] == kind and m["version"] == version and m["weight"] == weight)
        recognition = [("5", w) for w in ["baseline", "thai_ft_v3", "thai_ft_v4", "thai_ft_v6"]] + [("6", "thai_ft_v1")]
        configs = []
        for det in ["baseline", "thai_ft_v2"]:
            for version, rec in recognition:
                configs.append(("det_rec", det, version, rec))
        configs += [("rec", None, "5", "baseline"), ("rec", None, "6", "thai_ft_v1")]
        pipelines = []
        for index, (mode, det, version, rec) in enumerate(configs):
            config = await diag.checked(client, "POST", "/api/pipelines", json={
                "name": f"SYNTHETIC_FULL_SCALE_{label}_{index}_{uuid4().hex[:6]}", "source": "custom",
                "execution_mode": mode, "enabled": True,
                "det_model_id": model("det", "6", det)["id"] if det else None,
                "rec_model_id": model("rec", version, rec)["id"],
            })
            pipelines.append((config["pipeline_id"], version, rec))
        await client.post(MOCK + "/diagnostics/profile/sized")
        await client.post(MOCK + "/diagnostics/identity/true")
        await client.post(MOCK + "/diagnostics/failure/" + ("thai_ft_v6" if failure else "none"))
        for repetition in range(repetitions):
            image = Image.new("RGB", (4000, 2400), "white")
            draw = ImageDraw.Draw(image)
            fields = []
            for i in range(30):
                x, y = (i % 5) * 800, (i // 5) * 400
                draw.rectangle((x, y, x + 799, y + 399), fill=(i + 1, 120, 200))
                fields.append({"id": str(uuid4()), "field_index": i + 1, "source": "manual",
                               "roi": {"x1": x, "y1": y, "x2": x + 800, "y2": y + 400},
                               "ground_truth_raw": f"SYNTHETIC {i+1:02d}"})
            buf = BytesIO(); image.save(buf, format="PNG"); image.close(); png = buf.getvalue()
            document = await diag.checked(client, "POST", "/api/documents", files={"file": ("synthetic-30-fields.png", png, "image/png")})
            case = await diag.checked(client, "POST", "/api/test-cases", json={"document_id": document["id"], "workflow": "global", "ground_truth_raw": "synthetic GT supplied; no prefill"})
            cid = case["id"]
            await diag.checked(client, "PUT", f"/api/test-cases/{cid}/global-fields", json={"fields": fields, "confirmed": True})
            offset = len((await client.get(MOCK + "/diagnostics")).json()["events"])
            started = time.time()
            row = {"label": label, "repetition": repetition + 1, "failure_injection": failure,
                   "fields": 30, "pipelines": 12, "expected_results": 360, "case_id": cid,
                   "asset_sha256": hashlib.sha256(png).hexdigest(), "container_before": diag.inspect()}
            try:
                response = await client.post(BASE + f"/api/test-cases/{cid}/run", json={"pipelines": [p[0] for p in pipelines]})
                row["http_status"] = response.status_code
                if response.status_code == 200:
                    runs = response.json()["runs"]
                    saved = await diag.checked(client, "GET", f"/api/test-cases/{cid}")
                    correct = 0; failed = 0; box_correct = 0; confidence_correct = 0; trace_correct = 0
                    for (pid, version, variant), run in zip(pipelines, runs):
                        assert run["pipeline_id"] == pid
                        assert len(run["fields"]) == 30
                        assert [f["global_field_id"] for f in run["fields"]] == [f["id"] for f in fields]
                        for index, prediction in enumerate(run["fields"]):
                            if failure and variant == "thai_ft_v6":
                                failed += prediction["status"] == "error"
                                continue
                            correct += prediction["status"] == "success" and prediction["ocr_text"] == f"SYNTHETIC {index+1:02d} v{version} {variant}"
                            confidence_correct += prediction["confidence"] == .95
                            diagnostic = prediction["diagnostics"]
                            trace_correct += bool(diagnostic.get("gateway_request_id") and diagnostic.get("request_id"))
                            boxes = diagnostic.get("boxes", [])
                            roi = fields[index]["roi"]
                            box_correct += bool(boxes and all(roi["x1"] <= point[0] <= roi["x2"] and roi["y1"] <= point[1] <= roi["y2"] for box in boxes for point in box["polygon"]))
                    ids = [f["id"] for run in saved["runs"] for f in run["fields"]]
                    row.update(correct_results=correct, expected_injected_failures=failed,
                               successful_pipelines=sum(r["status"] == "success" for r in runs),
                               confidence_correct=confidence_correct, geometry_in_bounds=box_correct,
                               trace_correct=trace_correct, persisted_fields=len(ids), duplicate_field_ids=len(ids)-len(set(ids)),
                               run_times=[{k: r.get(k) for k in ["pipeline_id", "processing_time_ms", "wall_time_ms", "run_wall_time_ms", "total_field_compute_ms", "gateway_duration_ms"]} for r in runs])
                    expected_success = 300 if failure else 360
                    row["correctness_pass"] = correct == expected_success and confidence_correct == expected_success and trace_correct == expected_success and box_correct >= (240 if failure else 300) and len(ids) == 360 and len(set(ids)) == 360 and failed == (60 if failure else 0)
            except (httpx.RequestError, AssertionError) as exc:
                row["harness_or_http_error"] = type(exc).__name__
            ended = time.time(); row["wall_time_ms"] = round((ended-started)*1000, 2)
            row["resources"] = diag.summarize(started, ended)
            row["container_after"] = diag.inspect()
            events = (await client.get(MOCK + "/diagnostics")).json()["events"][offset:]
            row["gateway_calls"] = len(events)
            row["gateway_http_errors"] = [e["status"] for e in events if e.get("status", 200) >= 400]
            row["max_batch_images"] = max((e["count"] for e in events), default=0)
            row["started_at_epoch"] = started
            report["runs"].append(row); OUT.write_text(json.dumps(report, indent=2)+"\n")
            print(json.dumps({k: row.get(k) for k in ["label", "repetition", "http_status", "correct_results", "correctness_pass", "gateway_calls", "wall_time_ms"]} | {"rss": row["resources"]["peak_rss_bytes"], "cgroup": row["resources"]["peak_cgroup_bytes"]}), flush=True)
            if not row.get("correctness_pass") or row["container_after"]["state"]["OOMKilled"]:
                break
        await client.post(MOCK + "/diagnostics/failure/none")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], int(sys.argv[2]), "--failure" in sys.argv))
