import httpx
import pytest

from app.core.config import Settings
from app.integrations.model_gateway import (
    GatewayError,
    ModelGatewayClient,
    preserve_leaf_predictions,
    retry_after_seconds,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def gateway(monkeypatch, handler):
    client = ModelGatewayClient(Settings(model_gateway_api_key="synthetic-test-key", model_gateway_base_url="https://gateway.test"))
    monkeypatch.setattr(client, "_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return client


@pytest.mark.anyio
@pytest.mark.parametrize("kind,item", [
    ("text_detection_batch", {"dt_polys": [[[0, 0], [9, 0], [9, 5], [0, 5]]], "dt_scores": [.9]}),
    ("text_recognition_batch", {"rec_text": "กิ่ ABC 12", "rec_score": .95}),
])
async def test_current_leaf_raw_only_preserves_predictions_not_transport(monkeypatch, kind, item):
    payload = {"data": {"contract_version": "leaf-inference-v1", "kind": kind, "count": 2,
                        "raw_output": [dict(item, input_img=[[1]*100], input_path="private.png"), item]},
               "meta": {"request_id": "upstream", "duration_ms": 12}}
    client = gateway(monkeypatch, lambda _: httpx.Response(200, json=payload))
    result = await client.send({"method": "POST", "url": "https://gateway.test/api/v1/text-detection-batches", "headers": {}, "params": {"version": "6"}})
    assert result["data"]["results"] == [item, item]
    if kind == "text_detection_batch":
        assert result["data"]["result"]["results"] == [item, item]
    assert "raw_output" not in result["data"]
    assert "input_img" not in str(result) and "private.png" not in str(result)
    assert result["meta"]["request_id"] == "upstream"


@pytest.mark.anyio
async def test_429_bounded_retry_but_never_422(monkeypatch):
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(429 if len(requests) == 1 else 200,
            headers={"Retry-After": "0"}, json={"data": {}, "meta": {}} if len(requests)>1 else {"error": {"code": "RATE_LIMIT_EXCEEDED"}})
    client = gateway(monkeypatch, respond)
    result = await client.send({"method": "POST", "url": "https://gateway.test/api/v1/text-recognition-batches", "headers": {}, "params": {"version": "5"}})
    assert result == {"data": {}, "meta": {}}
    assert len(requests) == 2
    requests.clear()
    monkeypatch.setattr(client, "_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: (requests.append(request) or httpx.Response(422, json={"error": {"code": "UPSTREAM_MODEL_ERROR"}})))))
    with pytest.raises(GatewayError):
        await client.send({"method": "POST", "url": "https://gateway.test/api/v1/text-recognition-batches", "headers": {}, "params": {"version": "5"}})
    assert len(requests) == 1


def test_malformed_raw_results_are_not_fabricated():
    with pytest.raises(GatewayError, match="count or schema"):
        preserve_leaf_predictions({"contract_version":"leaf-inference-v1", "kind":"text_detection_batch", "count":2, "raw_output":[{"dt_polys":[]}]})


@pytest.mark.parametrize("kind,items", [("text_recognition_batch",[{"rec_text":None}]),("text_detection_batch",[{"dt_polys":None}]),("text_recognition_batch",[{"rec_text":"x"}]*31)])
def test_invalid_raw_prediction_or_excessive_count_is_rejected(kind,items):
    with pytest.raises(GatewayError):
        preserve_leaf_predictions({"contract_version":"leaf-inference-v1","kind":kind,"count":len(items),"raw_output":items})


@pytest.mark.parametrize("value,expected", [("12",12), ("0",0), ("-2",0), ("invalid",None), ("nan",None)])
def test_retry_after_parsing(value, expected):
    assert retry_after_seconds(value) == expected


@pytest.mark.anyio
async def test_retry_after_above_budget_is_not_ignored(monkeypatch):
    calls=[]
    client=gateway(monkeypatch, lambda request: (calls.append(request) or httpx.Response(429, headers={"Retry-After":"60"}, json={"error":{"code":"RATE_LIMIT_EXCEEDED"}})))
    with pytest.raises(GatewayError):
        await client.send({"method":"POST", "url":"https://gateway.test/api/v1/text-recognition-batches", "headers":{}, "params":{}})
    assert len(calls)==1
