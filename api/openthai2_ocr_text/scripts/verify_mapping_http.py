"""Compare synthetic Single/Batch responses without changing their coordinates."""
import argparse
import io
import json
import math
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PIL import Image


def fixtures():
    source = Path(__file__).resolve().parents[1] / "tests/fixtures/synthetic-thai-english.png"
    values = []
    with Image.open(source) as image:
        for label, angle in [("original", 0), ("rotated90", 90), ("rotated180", 180),
                ("rotated270", 270), ("skewed7", 7)]:
            rotated = image.rotate(angle, expand=True, fillcolor="white")
            try:
                with io.BytesIO() as stream:
                    rotated.save(stream, "PNG")
                    values.append((label, stream.getvalue(), rotated.size))
            finally:
                rotated.close()
    with Image.new("RGB", (100, 80), "white") as blank, io.BytesIO() as stream:
        blank.save(stream, "PNG")
        values.append(("blank", stream.getvalue(), blank.size))
    return values


def verify(url):
    if urlsplit(url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Use the local standalone service for this synthetic regression")
    key = os.environ.get("OPENTHAI_API_KEY", "")
    if not key:
        raise ValueError("Configure the private local service key")
    inputs = fixtures()
    cases = []
    with httpx.Client(base_url=url, headers={"X-API-Key": key}, timeout=120,
            trust_env=False, follow_redirects=False) as client:
        for label, content, dimensions in inputs:
            response = client.post("/api/v1/ocr-text", files={"image": ("synthetic.png", content, "image/png")})
            response.raise_for_status()
            data = response.json()["data"]
            assert data["image"] == {"width": dimensions[0], "height": dimensions[1]}
            for line in data["lines"]:
                assert len(line["box"]) == 4
                assert all(len(point) == 2 and all(math.isfinite(value) for value in point) for point in line["box"])
            assert data["confidence"] is None
            cases.append({"label": label, "data": data})
        uploads = [("images", ("synthetic.png", content, "image/png")) for _, content, _ in inputs]
        uploads.insert(2, ("images", ("corrupt.png", b"corrupt", "image/png")))
        response = client.post("/api/v1/ocr-text-batches", files=uploads)
        response.raise_for_status()
        data = response.json()["data"]
        assert (data["total"], data["succeeded"], data["failed"]) == (7, 6, 1)
        assert [item["index"] for item in data["results"]] == list(range(7))
        valid = []
        for item in data["results"]:
            if item["index"] == 2:
                assert item["status"] == "error" and item["result"] is None
                assert item["error"]["code"] == "INVALID_IMAGE"
            else:
                assert item["status"] == "success" and item["error"] is None
                valid.append(item["result"])
        assert valid == [case["data"] for case in cases]
        assert cases[0]["data"]["text"] and len(cases[0]["data"]["lines"]) >= 2
        assert cases[-1]["data"]["text"] == "" and cases[-1]["data"]["lines"] == []
    return {"synthetic_only": True, "single_cases": cases, "batch": data, "single_batch_equal": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8091")
    parser.add_argument("--output", required=True, help="Local synthetic response evidence file")
    args = parser.parse_args()
    report = verify(args.url)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"single_cases": len(report["single_cases"]), "batch_items": report["batch"]["total"],
        "single_batch_equal": True, "synthetic_only": True}))
