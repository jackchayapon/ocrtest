"""Compare actual sequential single/batch HTTP using packaged synthetic input."""
import argparse
import hashlib
import io
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PIL import Image


def benchmark(url, rounds=3):
    if urlsplit(url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Use a local service or an authorized local staging tunnel for this benchmark")
    fixture = (Path(__file__).resolve().parents[1]/"tests/fixtures/synthetic-thai-english.png").read_bytes()
    with Image.new("RGB", (320, 180), "white") as image, io.BytesIO() as stream:
        image.save(stream, "JPEG")
        blank = stream.getvalue()
    images = [(fixture, "image/png"), (blank, "image/jpeg")]
    headers = {"X-API-Key": os.environ["OPENTHAI_API_KEY"]} if os.environ.get("OPENTHAI_API_KEY") else {}
    trials = []
    with httpx.Client(base_url=url, headers=headers, timeout=600, follow_redirects=False, trust_env=False) as client:
        readiness = client.get("/api/v1/readiness")
        readiness.raise_for_status()
        cold_started = time.perf_counter()
        first = client.post("/api/v1/ocr-text", files={"image": ("synthetic.png", fixture, "image/png")})
        first.raise_for_status()
        first_latency = time.perf_counter()-cold_started
        expected = [first.json()["data"]]
        other = client.post("/api/v1/ocr-text", files={"image": ("blank.jpg", blank, "image/jpeg")})
        other.raise_for_status()
        expected.append(other.json()["data"])
        assert expected[0]["text"] and expected[1]["text"] == ""
        for count in (1, 2, 4, 8):
            for trial in range(rounds):
                for mode in ("single", "batch"):
                    started_at = time.time()
                    started = time.perf_counter()
                    latencies = []
                    response_bytes = 0
                    if mode == "single":
                        results = []
                        for index in range(count):
                            content, mime = images[index % 2]
                            tick = time.perf_counter()
                            response = client.post("/api/v1/ocr-text", files={"image": ("synthetic", content, mime)})
                            response.raise_for_status()
                            latencies.append(time.perf_counter()-tick)
                            response_bytes += len(response.content)
                            results.append(response.json()["data"])
                        request_count = count
                    else:
                        uploads = [("images", ("synthetic", images[index % 2][0], images[index % 2][1])) for index in range(count)]
                        response = client.post("/api/v1/ocr-text-batches", files=uploads)
                        response.raise_for_status()
                        data = response.json()["data"]
                        assert data["total"] == data["succeeded"] == count and data["failed"] == 0
                        assert [item["index"] for item in data["results"]] == list(range(count))
                        results = [item["result"] for item in data["results"]]
                        response_bytes = len(response.content)
                        request_count = 1
                    elapsed = time.perf_counter()-started
                    assert results == [expected[index % 2] for index in range(count)]
                    trials.append({"count": count, "trial": trial+1, "mode": mode, "warm": True,
                        "started_at": started_at, "ended_at": time.time(), "wall_seconds": elapsed,
                        "amortized_seconds_per_image": elapsed/count, "single_image_latencies": latencies,
                        "images_per_second": count/elapsed, "http_requests": request_count,
                        "response_bytes": response_bytes, "errors": 0, "output_matches_single": True})
        partial = client.post("/api/v1/ocr-text-batches", files=[
            ("images", ("synthetic.png", fixture, "image/png")), ("images", ("invalid.png", b"corrupt", "image/png")),
            ("images", ("blank.jpg", blank, "image/jpeg"))])
        partial.raise_for_status()
        assert [item["status"] for item in partial.json()["data"]["results"]] == ["success", "error", "success"]
        assert partial.json()["data"]["results"][1]["error"]["code"] == "INVALID_IMAGE"
    return {"readiness": readiness.json(), "first_single_after_startup_seconds": first_latency,
        "fixture_sha256": hashlib.sha256(fixture).hexdigest(), "reference_text_sha256": hashlib.sha256(expected[0]["text"].encode()).hexdigest(),
        "reference_characters": len(expected[0]["text"]), "reference_lines": len(expected[0]["lines"]),
        "real_model_http": True, "partial_failure_http": partial.status_code, "trials": trials}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8091")
    parser.add_argument("--rounds", type=int, default=3, choices=range(1, 6))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = benchmark(args.url, args.rounds)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"trials": len(report["trials"]), "real_model_http": True, "errors": 0, "output_matches_single": True}))
