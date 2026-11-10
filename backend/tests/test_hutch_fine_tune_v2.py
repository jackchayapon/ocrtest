import asyncio

import httpx
import pytest

from app.db.models import PipelineConfig
from app.integrations.model_gateway import GatewayError
from app.pipelines.hutch_fine_tune_v2 import HutchFineTuneV2PipelineAdapter
from app.services.image_service import ImageService
from tests.test_benchmark_pipeline import parts
from tests.test_global_layout import layout
from tests.upstream_fixture import response

SLUG = "hutch_fine_tune_v2"
ENDPOINT = "/api/v1/text-recognition-batches"
pytestmark = pytest.mark.usefixtures("registered_catalog")


@pytest.mark.parametrize("leaf", [False, True])
@pytest.mark.parametrize("score", [None, 0.91])
def test_rec_only_exact_crop_contract_normalization_and_raw_metadata(settings, gateway, png, leaf, score):
    item = {"rec_text" if leaf else "text": "ภาษาไทย 123", "rec_score" if leaf else "confidence": score,
            "model": "stale-model"}
    data = {"count": 1, "results": [item]}
    if leaf:
        data.update(contract_version="leaf-inference-v1", kind="text_recognition_batch")
    payload = {"data": data, "meta": {"request_id": "upstream", "duration_ms": 12,
                                        "service": "recognition", "model": "stale-model"}}
    gateway[0]["handler"] = lambda r: httpx.Response(200, json=payload)
    config = PipelineConfig(pipeline_id=SLUG, name="Hutch fine tune v2", enabled=True,
                            query_params={"version": "6", "engine": "ignored"})
    roi = dict(x1=40, y1=30, x2=270, y2=150)
    with ImageService.open(png) as original:
        crop = ImageService(settings).canonical_crop(original, roi)
        result = asyncio.run(HutchFineTuneV2PipelineAdapter(config, settings).run(
            original_image=original, cropped_image=crop, roi=roi, request_id="rec-only"))
    assert len(gateway[1]) == 1
    request = gateway[1][0]
    assert request.url.path == ENDPOINT
    assert dict(request.url.params) == {"version": "5", "model": "thai_ft_v2"}
    assert parts(request) == [("images", crop.png)]
    assert request.headers["x-request-id"] == "rec-only"
    assert result.text == "ภาษาไทย 123" and result.confidence == score
    assert result.raw_response == payload and result.boxes == []
    assert result.diagnostics["input_sha256"] == crop.sha256
    assert (result.diagnostics["input_width"], result.diagnostics["input_height"]) == (230, 120)
    assert result.diagnostics["gateway_request_id"] == "upstream"
    assert result.diagnostics["gateway_duration_ms"] == 12


def test_requires_prebuilt_crop(settings):
    adapter = HutchFineTuneV2PipelineAdapter(PipelineConfig(pipeline_id=SLUG, enabled=True), settings)
    with pytest.raises(GatewayError):
        asyncio.run(adapter.run())


def test_global_identity_order_shared_gt_history_and_partial_failure(client, document, gateway, settings, png):
    case, fields = layout(client, document, prefill=False)
    root = f"/api/test-cases/{case['id']}"
    seen = []

    def handler(request):
        if request.url.path != ENDPOINT:
            return response(request)
        batch = parts(request)
        start = len(seen)
        seen.extend([part] for part in batch)
        return httpx.Response(200, json={"data": {"count": len(batch), "results": [
            {"text": f"ไทย {start+i+1}", "confidence": 0.9} for i in range(len(batch))]}, "meta": {}})

    gateway[0]["handler"] = handler
    result = client.post(root + "/run", json={"pipelines": ["mint", SLUG]})
    assert result.status_code == 200
    runs = {r["pipeline_id"]: r for r in result.json()["runs"]}
    new = runs[SLUG]
    assert new["status"] == "success" and new["final_text"] == "ไทย 1\nไทย 2"
    assert [f["global_field_id"] for f in new["fields"]] == [f["id"] for f in fields]
    with ImageService.open(png) as original:
        for i, field in enumerate(fields):
            crop = ImageService(settings).canonical_crop(original, field["roi"])
            assert seen[i] == [("images", crop.png)]
            assert new["fields"][i]["diagnostics"]["input_sha256"] == crop.sha256
            assert runs["mint"]["fields"][i]["diagnostics"]["input_sha256"] == crop.sha256
    client.put(root + "/ground-truth", json={"ground_truth_raw": new["final_text"]})
    for i, field in enumerate(fields):
        client.put(root + f"/global-fields/{field['id']}/ground-truth",
                   json={"ground_truth_raw": f"ไทย {i+1}"})
    evaluated = client.post(root + "/evaluate", json={"mode": "auto", "global_field_ids": [f["id"] for f in fields]})
    assert evaluated.status_code == 200, evaluated.text
    saved = client.get(root).json()
    new = next(r for r in saved["runs"] if r["pipeline_id"] == SLUG)
    assert new["document_evaluation"]["exact_match"]
    assert all(f["evaluation"]["exact_match"] for f in new["fields"])
    assert client.get("/api/history", params={"pipeline": SLUG}).json()[0]["id"] == case["id"]
    gateway[0]["handler"] = lambda r: httpx.Response(503, json={"error": {"code": "SERVICE_UNAVAILABLE"}}) if r.url.path == ENDPOINT else response(r)
    second, _ = layout(client, document)
    failed = client.post(f"/api/test-cases/{second['id']}/run", json={"pipelines": ["mint", SLUG]}).json()
    statuses = {r["pipeline_id"]: r["status"] for r in failed["runs"]}
    assert statuses["mint"] == "success" and statuses[SLUG] != "success"


def test_registration_fixed_route_unknown_readiness(client):
    config = next(c for c in client.get("/api/pipelines").json() if c["pipeline_id"] == SLUG)
    assert config["name"] == "Hutch fine tune v2"
    assert config["endpoint"] == ENDPOINT and config["file_field_name"] == "images"
    assert config["query_params"] == {"version": "5", "model": "thai_ft_v2"}
    for change in ({"query_params": {"version": "6"}}, {"endpoint": "/other"}, {"file_field_name": "image"}):
        assert client.put(f"/api/pipelines/{SLUG}", json=change).status_code == 422
    assert client.post(f"/api/pipelines/{SLUG}/test-connection").json()["status"] == "gateway_connected"
