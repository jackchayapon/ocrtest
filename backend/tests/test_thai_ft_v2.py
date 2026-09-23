import asyncio
import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.db.models import PipelineConfig
from app.integrations.model_gateway import GatewayError
from app.pipelines.benchmark import (
    DETECTION_ENDPOINT,
    RECOGNITION_ENDPOINT,
    BenchmarkPipelineAdapter,
)
from app.pipelines.thai_ft_v2 import ThaiFTV2PipelineAdapter
from app.services.field_service import compare_field
from app.services.image_service import ImageService
from app.services.pipeline_manager import PipelineManager
from tests.test_benchmark_pipeline import parts


def live_fixtures():
    root = Path(__file__).parent / "fixtures"
    return [json.loads((root / f"thai-ft-v2-{stage}.json").read_text(encoding="utf-8"))
            for stage in ("det", "rec")]


def execute(settings):
    config = PipelineConfig(pipeline_id="thai_ft_v2", name="Thai FT v2", enabled=True,
                            query_params={"version": "5", "engine": "ignored"})
    with Image.new("RGB", (1100, 400), "white") as original:
        roi = dict(x1=20, y1=30, x2=1020, y2=380)
        crop = ImageService(settings).canonical_crop(original, roi)
        return asyncio.run(ThaiFTV2PipelineAdapter(config, settings).run(
            original_image=original, cropped_image=crop, roi=roi, request_id="thai-test")), crop


def test_live_fixture_contract_order_geometry_metadata_and_no_v5_fallback(settings, gateway):
    det, rec = live_fixtures()
    gateway[0]["handler"] = lambda r: httpx.Response(
        200, json=det if r.url.path == DETECTION_ENDPOINT else rec)
    result, crop = execute(settings)
    calls = gateway[1]
    assert [r.url.path for r in calls] == [DETECTION_ENDPOINT, RECOGNITION_ENDPOINT]
    assert all(dict(r.url.params) == {"version": "6", "model": "thai_ft_v2"} for r in calls)
    assert all(r.headers["authorization"] == "Bearer test-gateway-secret" for r in calls)
    assert [r.headers["x-request-id"] for r in calls] == ["thai-test_det", "thai-test_rec_0"]
    assert parts(calls[0]) == [("images", crop.png)]
    polygons = det["data"]["result"]["results"][0]["dt_polys"]
    with ImageService.open(crop.png) as image:
        assert parts(calls[1]) == [("images", ImageService(settings).rectify_quad(image, p))
                                  for p in polygons]
    assert [b["text"] for b in result.boxes] == [r["text"] for r in rec["data"]["results"]]
    assert [b["crop_polygon"] for b in result.boxes] == polygons
    assert result.boxes[0]["polygon"][0] == [polygons[0][0][0]+20, polygons[0][0][1]+30]
    assert result.confidence == pytest.approx(sum(r["confidence"] for r in rec["data"]["results"])/2)
    assert result.diagnostics["recognizer_model"] == "PP-OCRv6_medium_rec"
    assert result.diagnostics["detector_model"] == "PP-OCRv6_medium_det"
    assert result.diagnostics["gateway_duration_ms"] == pytest.approx(
        det["meta"]["duration_ms"] + rec["meta"]["duration_ms"])
    assert result.raw_response["recognition_batches"][0] == rec
    assert all(r["model"] == "th_PP-OCRv5_mobile_rec" for r in rec["data"]["results"])
    assert result.raw_response["composition"]["recognition_version"] == "6"
    assert result.diagnostics["crop_sha256"] == crop.sha256


def test_multiple_batches_unicode_order_and_missing_selection(settings, gateway):
    det, _ = live_fixtures()
    row = det["data"]["result"]["results"][0]
    row["dt_polys"] *= 5
    row["dt_scores"] *= 5
    count = 0

    def handler(request):
        nonlocal count
        assert dict(request.url.params) == {"version": "6", "model": "thai_ft_v2"}
        if request.url.path == DETECTION_ENDPOINT:
            return httpx.Response(200, json=det)
        n = len(parts(request))
        items = [{"text": f"ภาษาไทย {i}", "model": "th_PP-OCRv5_mobile_rec"}
                 for i in range(count, count+n)]
        count += n
        return httpx.Response(200, json={"data": {"results": items, "count": n}, "meta": {}})

    gateway[0]["handler"] = handler
    result, _ = execute(settings)
    assert result.text == "\n".join(f"ภาษาไทย {i}" for i in range(10))
    assert [len(parts(r)) for r in gateway[1]] == [1, 8, 2]
    assert result.confidence is None
    assert result.diagnostics["recognizer_model"] == "Thai FT v2 REC V6"


@pytest.mark.parametrize("adapter", [BenchmarkPipelineAdapter, ThaiFTV2PipelineAdapter])
def test_current_leaf_recognition_contract_keeps_queries_and_raw_payload(settings, gateway, adapter):
    det, _ = live_fixtures()
    rec = json.loads((Path(__file__).parent / "fixtures/thai-ft-v2-rec-leaf.json").read_text(encoding="utf-8"))
    row = det["data"]["result"]["results"][0]
    row["dt_polys"] = row["dt_polys"][:1]
    row["dt_scores"] = row["dt_scores"][:1]
    gateway[0]["handler"] = lambda r: httpx.Response(200, json=det if r.url.path == DETECTION_ENDPOINT else rec)
    with Image.new("RGB", (1000, 350), "white") as image:
        roi = dict(x1=0, y1=0, x2=1000, y2=350)
        crop = ImageService(settings).canonical_crop(image, roi)
        result = asyncio.run(adapter(PipelineConfig(pipeline_id="fixture", name="fixture", enabled=True), settings).run(
            original_image=image, cropped_image=crop, roi=roi))
    item = rec["data"]["results"][0]
    assert result.raw_text == item["rec_text"]
    assert result.boxes[0]["text"] == item["rec_text"]
    assert result.confidence == item["rec_score"]
    assert result.raw_response["recognition_batches"][0] == rec
    expected = [{"version": "6"}, {"version": "5"}] if adapter is BenchmarkPipelineAdapter else [
        {"version": "6", "model": "thai_ft_v2"}, {"version": "6", "model": "thai_ft_v2"}]
    assert [dict(r.url.params) for r in gateway[1]] == expected


@pytest.mark.parametrize("failure", ["count", "polygon", "upstream"])
def test_invalid_response_or_failure_does_not_retry_rec_v5(settings, gateway, failure):
    det, rec = live_fixtures()
    if failure == "polygon":
        det["data"]["result"]["results"][0]["dt_polys"][0] = [[0, 0]]
    if failure == "count":
        rec["data"]["count"] = 99

    def handler(r):
        if r.url.path == RECOGNITION_ENDPOINT and failure == "upstream":
            return httpx.Response(503, json={"error": {"code": "SERVICE_UNAVAILABLE"}})
        return httpx.Response(200, json=det if r.url.path == DETECTION_ENDPOINT else rec)

    gateway[0]["handler"] = handler
    with pytest.raises(GatewayError):
        execute(settings)
    assert all(dict(r.url.params) == {"version": "6", "model": "thai_ft_v2"} for r in gateway[1])


@pytest.mark.parametrize("source", ["auto", "manual"])
def test_roi_fields_persistence_and_dynamic_views(client, document, source):
    roi = dict(x1=40, y1=30, x2=270, y2=150)
    case = client.post("/api/test-cases", json=dict(
        document_id=document["id"], roi=roi, roi_source=source,
        ground_truth_raw="ภาษาไทย", category_codes=["thai_text"])).json()
    ids = list(PipelineManager.adapter_classes)
    runs = client.post(f"/api/test-cases/{case['id']}/run", json={"pipelines": ids}).json()["runs"]
    by_id = {r["pipeline_id"]: r for r in runs}
    assert all(r["status"] == "success" for r in runs)
    run = by_id["thai_ft_v2"]
    assert run["roi"] == roi and run["input_width"] == 230 and run["input_height"] == 120
    assert all(by_id[p]["crop_sha256"] == run["crop_sha256"] for p in ("mint", "hutch_crop", "benchmark"))
    assert by_id["hutch_full"]["input_width"] == (300 if source == "auto" else 230)
    field = run["fields"][0]
    assert field["geometry"]["polygon"] == run["boxes"][0]["polygon"]
    url = f"/api/test-cases/{case['id']}/runs/{run['id']}/fields/{field['id']}"
    expected = compare_field(field["ocr_text"], "ภาษาไทย")
    for _ in range(2):
        assert client.post(url+"/check", json={"ground_truth_raw": "ภาษาไทย"}).json() == expected
    saved = client.get(f"/api/test-cases/{case['id']}").json()
    assert all(f["ground_truth_raw"] is None for r in saved["runs"] for f in r["fields"])
    confirmed = client.put(url+"/ground-truth", json={"ground_truth_raw": "ภาษาไทย", "confirmed": True})
    assert confirmed.json()["evaluation"] == expected
    saved = client.get(f"/api/test-cases/{case['id']}").json()
    for r in saved["runs"]:
        assert r["field_summary"]["confirmed_fields"] == (1 if r["pipeline_id"] == "thai_ft_v2" else 0)
    wrong = url.replace(run["id"], by_id["benchmark"]["id"])
    assert client.post(wrong+"/check", json={"ground_truth_raw": "x"}).status_code == 404
    assert client.get("/api/history", params={"pipeline": "thai_ft_v2"}).json()[0]["id"] == case["id"]
    assert client.get("/api/matrix", params={"pipeline": "thai_ft_v2"}).json()[0]["tests"] == 1
    errors = client.get("/api/analytics/errors", params={"pipeline": "thai_ft_v2"}).json()
    assert errors["total"] > 0 and all(e["pipeline_id"] == "thai_ft_v2" for e in errors["items"])


def test_registration_fixed_settings_and_unknown_readiness(client):
    configs = client.get("/api/pipelines").json()
    assert {c["pipeline_id"] for c in configs} == {"mint", "hutch_crop", "hutch_full", "benchmark", "thai_ft_v2"}
    config = next(c for c in configs if c["pipeline_id"] == "thai_ft_v2")
    assert config["query_params"] == {"version": "6", "model": "thai_ft_v2"}
    assert config["file_field_name"] == "images" and config["name"] == "Thai FT v2"
    for enabled in (False, True):
        assert client.put("/api/pipelines/thai_ft_v2", json={"enabled": enabled}).status_code == 200
    for value in ({"query_params": {"version": "5"}}, {"endpoint": "/other"},
                  {"request_format": "json_base64"}, {"file_field_name": "image"}):
        assert client.put("/api/pipelines/thai_ft_v2", json=value).status_code == 422
    assert client.post("/api/pipelines/thai_ft_v2/test-connection").json()["status"] == "unknown"
