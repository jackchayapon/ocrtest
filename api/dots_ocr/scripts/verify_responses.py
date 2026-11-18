"""Independently validate saved synthetic REAL HTTP responses, not test doubles."""

import argparse
import json
import math
from pathlib import Path


def verify(directory):
    report = json.loads((directory / "results.json").read_text(encoding="utf-8"))
    assert report["evidence_type"] == "REAL_MODEL_REAL_HTTP"
    assert report["readiness"]["status"] == 200
    checks = 0

    def check_data(data):
        nonlocal checks
        assert data["schema_version"] == "1.0"
        assert data["coordinate_frame"] == "input_image_pixels"
        assert data["reading_order"] == "model_sequence"
        assert data["confidence"] is None
        width, height = data["image"]["width"], data["image"]["height"]
        for index, element in enumerate(data["elements"]):
            assert element["index"] == index and element["confidence"] is None
            box = element["bbox"]
            if box is not None:
                assert element["geometry_status"] == "valid" and len(box) == 4
                assert all(math.isfinite(v) for v in box)
                assert 0 <= box[0] < box[2] <= width + 1e-8
                assert 0 <= box[1] < box[3] <= height + 1e-8
            else:
                assert element["geometry_status"] in {"absent", "out_of_bounds"}
            checks += 1
        assert data["text"] == "\n".join(
            e["text"] for e in data["elements"] if e["text"] is not None
        )
        assert data["tables"] == [
            e["index"] for e in data["elements"] if e["category"] == "Table"
        ]

    for record in report["requests"]:
        response = json.loads(
            (directory / record["response_file"]).read_text(encoding="utf-8")
        )
        if record["http_status"] == 200:
            data = response["data"]
            if "results" in data:
                assert [r["index"] for r in data["results"]] == list(
                    range(data["count"])
                )
                assert data["succeeded"] + data["failed"] == data["count"]
                for result in data["results"]:
                    if result["status"] == "success":
                        assert result["error"] is None
                        check_data(result["result"])
                    else:
                        assert result["result"] is None and result["error"]["code"]
            else:
                check_data(data)
        else:
            assert record["label"] in {"corrupt", "real-deadline"}, record
            assert response["error"]["code"] in {"INVALID_IMAGE", "INFERENCE_TIMEOUT"}
        checks += 1
    for count in [1, 2, 4, 8]:
        record = next(r for r in report["requests"] if r["label"] == f"batch{count}")
        assert record["exact_single_equivalence"] is True
    assert report["deadline_busy_status"] == 429
    assert (
        next(r for r in report["requests"] if r["label"] == "recovery-after-timeout")[
            "http_status"
        ]
        == 200
    )
    return {
        "status": "PASS",
        "requests": len(report["requests"]),
        "data_and_element_checks": checks,
        "scope": "Saved real synthetic HTTP artifacts, not OCR accuracy/capacity proof",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = verify(args.directory)
    (args.directory / "verification.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))
