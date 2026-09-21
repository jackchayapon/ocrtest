import asyncio
import json
from email.parser import BytesParser
from email.policy import default
from pathlib import Path

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

from app.db.models import PipelineConfig
from app.db.seed import seed_database
from app.integrations.model_gateway import GatewayError
from app.pipelines.benchmark import (
    DETECTION_ENDPOINT,
    RECOGNITION_ENDPOINT,
    BenchmarkPipelineAdapter,
)
from app.services.image_service import ImageService
from app.services.metrics_service import calculate_metrics


def parts(request):
    message = BytesParser(policy=default).parsebytes(
        b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n" + request.content
    )
    return [
        (p.get_param("name", header="content-disposition"), p.get_payload(decode=True))
        for p in message.iter_parts()
    ]


def config(**overrides):
    return PipelineConfig(
        pipeline_id="benchmark",
        name="Benchmark",
        enabled=True,
        endpoint=DETECTION_ENDPOINT,
        request_format="multipart",
        **overrides,
    )


def fixtures():
    root = Path(__file__).parent / "fixtures"
    det = json.loads((root / "benchmark-detection-v6.json").read_text(encoding="utf-8"))
    rec = json.loads((root / "benchmark-recognition-v5.json").read_text(encoding="utf-8"))
    # These are precisely the three DET polygons sent in the live ordering probe.
    result = det["data"]["result"]["results"][0]
    for key in ("dt_polys", "dt_scores"):
        result[key] = [result[key][i] for i in (14, 16, 10)]
    return det, rec


def execute(settings, *, roi=None, cfg=None):
    # Source includes an offset around the canonical input, so document geometry can be asserted.
    roi = roi or dict(x1=20, y1=30, x2=1020, y2=1350)
    with Image.new("RGB", (1100, 1400), "white") as original:
        crop = ImageService(settings).canonical_crop(original, roi)
        result = asyncio.run(
            BenchmarkPipelineAdapter(cfg or config(), settings).run(
                original_image=original, cropped_image=crop, roi=roi, request_id="bench-test"
            )
        )
        return result, crop


def test_verified_contract_chaining_order_crop_and_traces(settings, gateway):
    det, rec = fixtures()

    def handler(request):
        return httpx.Response(200, json=det if request.url.path == DETECTION_ENDPOINT else rec)

    gateway[0]["handler"] = handler
    result, crop = execute(
        settings, cfg=config(query_params={"model": "must-not-be-sent", "engine": "ignored"})
    )
    calls = gateway[1]
    assert len(calls) == 2
    assert str(calls[0].url).endswith(DETECTION_ENDPOINT + "?version=6")
    assert str(calls[1].url).endswith(RECOGNITION_ENDPOINT + "?version=5")
    assert all(r.headers["authorization"] == "Bearer test-gateway-secret" for r in calls)
    assert [r.headers["x-request-id"] for r in calls] == ["bench-test_det", "bench-test_rec_0"]
    assert parts(calls[0]) == [("images", crop.png)]
    rec_parts = parts(calls[1])
    assert len(rec_parts) == 3
    assert all(name == "images" for name, _ in rec_parts)
    polygons = det["data"]["result"]["results"][0]["dt_polys"]
    with ImageService.open(crop.png) as source:
        assert [png for _, png in rec_parts] == [
            ImageService(settings).rectify_quad(source, p) for p in polygons
        ]
    assert (
        result.raw_text == result.final_text == "\n".join(x["text"] for x in rec["data"]["results"])
    )
    assert [b["crop_polygon"] for b in result.boxes] == polygons
    assert result.boxes[0]["polygon"][0] == [polygons[0][0][0] + 20, polygons[0][0][1] + 30]
    assert result.confidence == pytest.approx(
        sum(x["confidence"] for x in rec["data"]["results"]) / 3
    )
    assert result.diagnostics["crop_sha256"] == crop.sha256
    assert result.diagnostics["gateway_duration_ms"] == pytest.approx(
        det["meta"]["duration_ms"] + rec["meta"]["duration_ms"]
    )
    assert result.raw_response["detection"]["meta"] == det["meta"]
    assert result.raw_response["recognition_batches"][0]["meta"] == rec["meta"]


def test_empty_detection_skips_recognition_and_has_no_fabricated_confidence(settings, gateway):
    det, _ = fixtures()
    det["data"]["result"]["results"][0] = {"dt_polys": [], "dt_scores": []}
    gateway[0]["handler"] = lambda request: httpx.Response(200, json=det)
    result, _ = execute(settings)
    assert result.raw_text == "" and result.boxes == [] and result.confidence is None
    assert len(gateway[1]) == 1


@pytest.mark.parametrize(
    "fault", ["det_count", "contract", "polygon", "scores", "rec_count", "rec_text"]
)
def test_invalid_upstream_never_silently_mispairs_results(settings, gateway, fault):
    det, rec = fixtures()
    if fault == "det_count":
        det["data"]["count"] = 2
    if fault == "contract":
        det["data"]["kind"] = "unexpected"
    if fault == "polygon":
        det["data"]["result"]["results"][0]["dt_polys"][0] = [[0, 0]]
    if fault == "scores":
        det["data"]["result"]["results"][0]["dt_scores"] = []
    if fault == "rec_count":
        rec["data"]["results"].pop()
    if fault == "rec_text":
        rec["data"]["results"][0]["text"] = None
    gateway[0]["handler"] = lambda r: httpx.Response(
        200, json=det if r.url.path == DETECTION_ENDPOINT else rec
    )
    with pytest.raises(GatewayError, match=".") as error:
        execute(settings)
    assert error.value.code == "INVALID_OCR_RESPONSE"


def test_multiple_recognition_batches_keep_order(settings, gateway):
    det, rec = fixtures()
    row = det["data"]["result"]["results"][0]
    row["dt_polys"] = row["dt_polys"] * 3
    row["dt_scores"] = row["dt_scores"] * 3
    sent = 0

    def handler(request):
        nonlocal sent
        if request.url.path == DETECTION_ENDPOINT:
            return httpx.Response(200, json=det)
        count = len(parts(request))
        items = [{"text": str(i)} for i in range(sent, sent + count)]
        sent += count
        return httpx.Response(200, json={"data": {"results": items, "count": count}, "meta": {}})

    gateway[0]["handler"] = handler
    result, _ = execute(settings)
    assert result.text == "\n".join(str(i) for i in range(9))
    assert [len(parts(r)) for r in gateway[1]] == [1, 8, 1]
    assert result.confidence is None and result.diagnostics["gateway_duration_ms"] is None


def test_batch_responses_still_redact_images_and_secrets(settings, gateway):
    det, rec = fixtures()
    det["data"]["raw_output"] = {"input_img": [1, 2], "token": "test-gateway-secret"}
    rec["data"]["results"][0]["extra"] = "data:image/png;base64,SECRETIMAGE"
    gateway[0]["handler"] = lambda r: httpx.Response(
        200, json=det if r.url.path == DETECTION_ENDPOINT else rec
    )
    result, _ = execute(settings)
    text = json.dumps(result.raw_response)
    assert "SECRETIMAGE" not in text and "test-gateway-secret" not in text
    assert result.raw_response["detection"]["data"]["raw_output"]["input_img"] == "[redacted]"


def test_benchmark_persistence_metrics_error_analysis_and_dynamic_views(client, case):
    response = client.post(f"/api/test-cases/{case['id']}/run", json={"pipelines": ["benchmark"]})
    assert response.status_code == 200
    run = response.json()["runs"][0]
    assert run["status"] == "success"
    assert run["metrics"]["exact_match"] is True
    updated = client.put(
        f"/api/test-cases/{case['id']}/ground-truth",
        json={"ground_truth_raw": "ไทย", "confirmed": True},
    ).json()
    assert updated["runs"][0]["metrics"] == calculate_metrics(run["final_text"], "ไทย")
    events = client.get(
        "/api/analytics/errors", params={"pipeline": "benchmark", "test_case_id": case["id"]}
    ).json()
    assert events["total"] > 0 and all(x["pipeline_id"] == "benchmark" for x in events["items"])
    rows = client.get(
        "/api/matrix", params={"pipeline": "benchmark", "category": "thai_text"}
    ).json()
    assert len(rows) == 1 and rows[0]["tests"] == 1 and rows[0]["evaluated_runs"] == 1
    history = client.get("/api/history", params={"pipeline": "benchmark"}).json()
    assert history[0]["id"] == case["id"]
    assert client.get(f"/api/test-cases/{case['id']}").json()["runs"][0]["raw_response"][
        "recognition_batches"
    ]


def test_benchmark_failure_isolated_from_existing_pipelines(client, case, gateway):
    original_handler = gateway[0]["handler"]

    def handler(r):
        if r.url.path == RECOGNITION_ENDPOINT:
            return httpx.Response(
                503, json={"error": {"code": "SERVICE_UNAVAILABLE", "request_id": "rec-failed"}}
            )
        return original_handler(r)

    gateway[0]["handler"] = handler
    runs = client.post(
        f"/api/test-cases/{case['id']}/run",
        json={"pipelines": ["mint", "hutch_crop", "hutch_full", "benchmark"]},
    ).json()["runs"]
    assert [r["status"] for r in runs] == ["success", "success", "success", "error"]
    assert runs[0]["crop_sha256"] == runs[1]["crop_sha256"] == runs[3]["crop_sha256"]
    assert runs[2]["crop_stage"] == "full_image" and runs[2]["input_width"] == 300
    assert runs[3]["gateway_request_id"] == "rec-failed"


def test_additive_seed_and_fixed_benchmark_settings(client, settings):
    with client.app.state.database.session_factory() as session:
        mint = session.scalar(select(PipelineConfig).where(PipelineConfig.pipeline_id == "mint"))
        mint.enabled = False
        mint.name = "Preserved"
        session.commit()
        seed_database(session, settings)
        seed_database(session, settings)
        rows = list(session.scalars(select(PipelineConfig)))
        assert len(rows) == 4 and mint.name == "Preserved" and mint.enabled is False
    assert client.put("/api/pipelines/benchmark", json={"enabled": False}).status_code == 200
    assert client.put("/api/pipelines/benchmark", json={"enabled": True}).status_code == 200
    for payload in (
        {"endpoint": "/other"},
        {"query_params": {"model": "thai_ft_v1"}},
        {"query_params": {"version": "6", "engine": "paddle"}},
        {"request_format": "json_base64"},
        {"file_field_name": "image"},
    ):
        assert client.put("/api/pipelines/benchmark", json=payload).status_code == 422
    assert client.post("/api/pipelines/benchmark/test-connection").json()["status"] == "unknown"


@pytest.mark.parametrize(
    "polygon",
    [
        [[0, 0], [0, 0], [0, 0], [0, 0]],
        [[-1, 0], [2, 0], [2, 2], [-1, 2]],
        [[0, 0], [4, 0], [4, float("nan")], [0, 4]],
    ],
)
def test_rectification_rejects_invalid_quad(settings, polygon):
    with Image.new("RGB", (10, 10)) as image:
        with pytest.raises(ValueError):
            ImageService(settings).rectify_quad(image, polygon)
