"""Independent PR13 review: synthetic transports only, no live inference."""
import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from app.core.config import Settings
from app.integrations import model_gateway as module
from app.integrations.model_gateway import (
    GatewayError,
    ModelGatewayClient,
    preserve_leaf_predictions,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def client(monkeypatch, handler):
    instance = ModelGatewayClient(Settings(_env_file=None, model_gateway_api_key="synthetic", model_gateway_base_url="https://review.invalid"))
    monkeypatch.setattr(instance, "_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return instance


def request():
    return {"method": "POST", "url": "https://review.invalid/api/v1/text-recognition-batches", "params": {"version": "5"}, "headers": {}}


def test_http_date_and_extreme_retry_after():
    future = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=20), usegmt=True)
    assert 18 <= module.retry_after_seconds(future) <= 20
    for value in (None, "inf", "1e999", "not a date"):
        assert module.retry_after_seconds(value) is None
    assert module.retry_after_seconds("999999999999") == 999999999999


@pytest.mark.anyio
async def test_concurrent_429_exhaustion_is_three_attempts_each(monkeypatch):
    calls, sleeps = [], []
    async def sleep(delay):
        sleeps.append(delay)
    monkeypatch.setattr(module.asyncio, "sleep", sleep)
    instance = client(monkeypatch, lambda r: (calls.append(r) or httpx.Response(429, headers={"Retry-After": "invalid"}, json={"error": {"code": "RATE_LIMIT_EXCEEDED"}})))
    results = await asyncio.gather(*(instance.send(request()) for _ in range(4)), return_exceptions=True)
    assert all(isinstance(r, GatewayError) and r.http_status == 429 for r in results)
    assert len(calls) == 12 and len(sleeps) == 8
    assert all(1 <= d <= 2.5 for d in sleeps)
    assert ModelGatewayClient.active_requests == 0


@pytest.mark.anyio
@pytest.mark.parametrize("status", [422, 500, 503])
async def test_non_429_is_not_retried(monkeypatch, status):
    calls = []
    instance = client(monkeypatch, lambda r: (calls.append(r) or httpx.Response(status, json={"error": {"code": "UPSTREAM_ERROR"}})))
    with pytest.raises(GatewayError):
        await instance.send(request())
    assert len(calls) == 1


@pytest.mark.anyio
async def test_timeout_after_retry_is_not_retried_again(monkeypatch):
    calls = []
    async def sleep(_):
        pass
    monkeypatch.setattr(module.asyncio, "sleep", sleep)
    def respond(r):
        calls.append(r)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {}})
        raise httpx.ReadTimeout("synthetic", request=r)
    instance = client(monkeypatch, respond)
    with pytest.raises(GatewayError) as error:
        await instance.send(request())
    assert error.value.code == "GATEWAY_TIMEOUT" and len(calls) == 2


@pytest.mark.anyio
async def test_cancellation_during_backoff_stops_retry(monkeypatch):
    calls = []
    async def sleep(_):
        raise asyncio.CancelledError()
    monkeypatch.setattr(module.asyncio, "sleep", sleep)
    instance = client(monkeypatch, lambda r: (calls.append(r) or httpx.Response(429, json={"error": {}})))
    with pytest.raises(asyncio.CancelledError):
        await instance.send(request())
    assert len(calls) == 1 and ModelGatewayClient.active_requests == 0


def test_structured_precedence_drops_transport_archive():
    authoritative = [{"rec_text": "structured", "rec_score": .9}]
    data = {"contract_version": "leaf-inference-v1", "kind": "text_recognition_batch", "count": 1, "results": authoritative, "raw_output": [{"rec_text": "different", "input_img": [1, 2]}]}
    preserve_leaf_predictions(data)
    assert data["results"] is authoritative and "raw_output" not in data


@pytest.mark.anyio
async def test_oversized_response_stops_before_normalization(monkeypatch):
    instance = client(monkeypatch, lambda r: httpx.Response(200, content=b" " * (1024 * 1024 + 1)))
    instance.settings.model_gateway_max_response_mb = 1
    with pytest.raises(GatewayError) as error:
        await instance.send(request())
    assert error.value.code == "RESPONSE_TOO_LARGE"
