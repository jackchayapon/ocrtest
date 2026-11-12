import asyncio
import json
from copy import deepcopy

import httpcore
import httpx
import pytest
from PIL import Image

from app.integrations.external_ocr import (
    ExternalClient,
    PinnedBackend,
    Provider,
    allowed_ip,
    get_provider,
    normalize_external,
    validate_url,
)
from app.integrations.model_gateway import GatewayError
from app.services.image_service import ImageService
from app.services.ocr_jobs import restore_config, snapshot
from tests.test_dynamic_pipelines import integrated
from tests.test_global_layout import layout
from tests.test_ocr_jobs import submit, wait_job

REGISTRATION = {"name": "OpenThai test", "endpoint": "https://ocr.example/api/v1/ocr-text",
                "readiness_url": "https://ocr.example/api/v1/readiness", "auth_mode": "bearer",
                "credential_env": "EXTERNAL_OCR_SECRET_TEST"}


@pytest.fixture
def external(settings, monkeypatch):
    settings.external_ocr_providers = json.dumps({"openthai": REGISTRATION})
    # Settings are mutable but normally receive SecretStr through validation.
    from pydantic import SecretStr
    settings.external_ocr_providers = SecretStr(settings.external_ocr_providers)
    monkeypatch.setenv("EXTERNAL_OCR_SECRET_TEST", "synthetic-provider-secret")
    calls = []
    behavior = {"handler": lambda request: httpx.Response(200, json={
        "data": {"text": "ไทย ABC", "lines": [], "confidence": None},
        "meta": {"request_id": "req_test", "duration_ms": 12}})}
    def handler(request):
        calls.append(request)
        return behavior["handler"](request)
    monkeypatch.setattr(ExternalClient, "client", lambda self: httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False, follow_redirects=False))
    return behavior, calls


def definition(**changes):
    return {"name": "OpenThai", "source": "external_api", "execution_mode": "external_api",
            "provider_id": "openthai", **changes}


def test_registration_serialization_and_snapshot(client, settings, external):
    catalog = client.get("/api/pipelines/external-providers")
    assert catalog.status_code == 200
    assert catalog.json()[0]["api_key_configured"] is True
    assert "credential_env" not in catalog.text and "synthetic-provider-secret" not in catalog.text
    created = client.post("/api/pipelines", json=definition())
    assert created.status_code == 201, created.text
    value = created.json()
    assert value["det_model_id"] is value["rec_model_id"] is value["integrated_options"] is None
    assert value["external_provider"]["provider_id"] == "openthai"
    assert "secret" not in created.text
    with client.app.state.database.session_factory() as session:
        from app.repositories.benchmark_repository import BenchmarkRepository
        record = BenchmarkRepository(session).config(value["pipeline_id"])
        frozen = snapshot(record)
        restored = restore_config(frozen)
        assert restored.integrated_options == record.integrated_options
        assert "credential" not in str(frozen)
    response = client.put(f"/api/pipelines/{value['pipeline_id']}/definition", json=definition(name="Renamed", enabled=False))
    assert response.json()["pipeline_id"] == value["pipeline_id"] and not response.json()["enabled"]


@pytest.mark.parametrize("changes", [dict(provider_id="unknown"), dict(endpoint="https://evil.example/ocr"),
    dict(api_key="public-secret"), dict(source="custom"), dict(execution_mode="rec"),
    dict(det_model_id="00000000-0000-0000-0000-000000000000")])
def test_public_cannot_register_destinations_or_credentials(client, external, changes):
    assert client.post("/api/pipelines", json=definition(**changes)).status_code == 422


@pytest.mark.parametrize("url", ["http://ocr.example/api", "https://user:pass@ocr.example/api",
    "https://ocr.example/api?token=abc", "https://ocr.example/api#fragment", "file:///etc/passwd",
    "https://ocr.example\\evil/api", "https://ocr.example:99999/api"])
def test_unsafe_url(url):
    with pytest.raises(ValueError):
        validate_url(url)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1",
    "169.254.169.254", "0.0.0.0", "::1", "::ffff:127.0.0.1", "fe80::1", "224.0.0.1",
    "64:ff9b::a9fe:a9fe", "fec0::1"])
def test_ssrf_addresses(address):
    assert not allowed_ip(address, False)
    assert not allowed_ip(address, True) or address in {"127.0.0.1", "::1", "::ffff:127.0.0.1"}


def test_dns_pinned_and_revalidated(monkeypatch):
    async def scenario():
        backend = PinnedBackend(False)
        loop = asyncio.get_running_loop()
        addresses, connected = ["93.184.216.34"], []
        async def resolve(*args, **kwargs):
            return [(None, None, None, None, (address, 443)) for address in addresses]
        async def connect(host, *args):
            connected.append(host)
            return "stream"
        monkeypatch.setattr(loop, "getaddrinfo", resolve)
        monkeypatch.setattr(backend.backend, "connect_tcp", connect)
        assert await backend.connect_tcp("approved.example", 443) == "stream"
        assert connected == ["93.184.216.34"]
        addresses[:] = ["127.0.0.1"]
        with pytest.raises(httpcore.ConnectError):
            await backend.connect_tcp("approved.example", 443)
        assert len(connected) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize("status", [301, 302, 307, 308, 401, 403, 429, 500, 503])
def test_errors_not_retried_or_followed(settings, external, status):
    behavior, calls = external
    behavior["handler"] = lambda request: httpx.Response(status, headers={"Location": "http://169.254.169.254/", "Retry-After": "5"})
    with pytest.raises(GatewayError) as error:
        asyncio.run(ExternalClient(settings, get_provider(settings, "openthai")).request("test", b"png"))
    assert error.value.code == f"EXTERNAL_HTTP_{status}"
    assert len(calls) == 1 and calls[0].url.host == "ocr.example"
    assert calls[0].headers["Authorization"] == "Bearer synthetic-provider-secret"


@pytest.mark.parametrize("payload", [[], {"data": {"text": 123}}, {"text": "synthetic-provider-secret"}])
def test_bad_response_or_credential_echo(settings, external, payload):
    behavior, _ = external
    behavior["handler"] = lambda request: httpx.Response(200, json=payload)
    with Image.new("RGB", (20, 20)) as image:
        crop = ImageService(settings).canonical_crop(image, None)
    with pytest.raises(GatewayError):
        provider = get_provider(settings, "openthai")
        value = asyncio.run(ExternalClient(settings, provider).request("test", crop.png))
        normalize_external(value, provider, crop, None)


def test_text_geometry_offsets_order_and_generic(settings):
    with Image.new("RGB", (100, 100)) as image:
        crop = ImageService(settings).canonical_crop(image, {"x1": 10, "y1": 20, "x2": 90, "y2": 80})
    payload = {"data": {"text": "right\nleft", "image": {"width": 80, "height": 60}, "lines": [
        {"text": "right", "confidence": .9, "box": [[40, 1], [70, 1], [70, 10], [40, 10]]},
        {"text": "left", "confidence": None, "box": [[1, 1], [30, 1], [30, 10], [1, 10]]}]}}
    original = deepcopy(payload)
    text, score, boxes, _ = normalize_external(payload, Provider(**REGISTRATION), crop, {"x1": 10, "y1": 20})
    assert text == "right\nleft" and score is None and boxes[0]["polygon"][0] == [50, 21]
    assert boxes[1]["confidence"] is None and payload == original
    generic = Provider(name="Generic", endpoint="https://ocr.example/ocr", response_adapter="text_json", text_path="result.text")
    assert normalize_external({"result": {"text": "ไทย"}}, generic, crop, None)[:3] == ("ไทย", None, [])


def test_connection_has_honest_scope(client, external):
    behavior, calls = external
    behavior["handler"] = lambda request: httpx.Response(200, json={"status": "ready"})
    pid = client.post("/api/pipelines", json=definition()).json()["pipeline_id"]
    result = client.post(f"/api/pipelines/{pid}/test-connection").json()
    assert result["status"] == "provider_ready" and "Inference has not been tested" in result["message"]
    assert len(calls) == 1 and calls[0].method == "GET"


def test_mixed_durable_jobs_evaluation_and_history(client, document, external):
    case, fields = layout(client, document)
    external_id = client.post("/api/pipelines", json=definition()).json()["pipeline_id"]
    internal_id = client.post("/api/pipelines", json=integrated()).json()["pipeline_id"]
    job = submit(client, case, [external_id, internal_id], "external-idempotency")
    final = wait_job(client, job["job_id"])
    assert final["status"] == "completed", final
    results = client.get(f"/api/ocr-jobs/{job['job_id']}/results").json()
    external_run = next(run for run in results["runs"] if run["pipeline_id"] == external_id)
    assert len(external_run["fields"]) == 2
    assert all(field["ocr_text"] == "ไทย ABC" for field in external_run["fields"])
    assert external_run["raw_response"]["external_provider"]["provider_id"] == "openthai"
    assert len(external[1]) == 2  # Hidden GT prefill uses the existing CDGS mock.
    assert submit(client, case, [external_id, internal_id], "external-idempotency")["job_id"] == job["job_id"]
    assert len(external[1]) == 2
    root = f"/api/test-cases/{case['id']}"
    for field in fields:
        assert client.put(root + f"/global-fields/{field['id']}/ground-truth", json={"ground_truth_raw": "ไทย ABC"}).status_code == 200
    evaluated = client.post(root + "/evaluate", json={"mode": "per_field", "global_field_ids": [field["id"] for field in fields]})
    assert evaluated.status_code == 200, evaluated.text
    assert "synthetic-provider-secret" not in evaluated.text
    assert client.get("/api/history?view=summary&latest=true").status_code == 200
    assert client.get("/api/matrix").status_code == 200


def test_failure_isolation_and_registration_change(client, case, external, settings):
    behavior, calls = external
    external_id = client.post("/api/pipelines", json=definition()).json()["pipeline_id"]
    internal_id = client.post("/api/pipelines", json=integrated()).json()["pipeline_id"]
    behavior["handler"] = lambda request: httpx.Response(503)
    job = submit(client, case, [external_id, internal_id])
    assert wait_job(client, job["job_id"])["status"] == "partial_success"
    runs = client.get(f"/api/ocr-jobs/{job['job_id']}/results").json()["runs"]
    assert {run["pipeline_id"]: run["status"] for run in runs} == {external_id: "error", internal_id: "success"}
    from pydantic import SecretStr
    settings.external_ocr_providers = SecretStr(json.dumps({"openthai": {**REGISTRATION, "endpoint": "https://changed.example/ocr"}}))
    previous_calls = len(calls)
    next_job = submit(client, case, [external_id])
    assert wait_job(client, next_job["job_id"])["status"] == "failed"
    assert len(calls) == previous_calls


def test_missing_key_timeout_large_response_and_no_inference_on_check(settings, external, monkeypatch):
    behavior, calls = external
    provider = get_provider(settings, "openthai")
    monkeypatch.delenv("EXTERNAL_OCR_SECRET_TEST")
    with pytest.raises(GatewayError, match="credential"):
        asyncio.run(ExternalClient(settings, provider).request("test", b"png"))
    assert not calls
    monkeypatch.setenv("EXTERNAL_OCR_SECRET_TEST", "synthetic-provider-secret")
    def timeout(request):
        raise httpx.ReadTimeout("private diagnostics")
    behavior["handler"] = timeout
    with pytest.raises(GatewayError) as error:
        asyncio.run(ExternalClient(settings, provider).request("test", b"png"))
    assert error.value.code == "EXTERNAL_TIMEOUT" and "private" not in str(error.value)
    behavior["handler"] = lambda request: httpx.Response(200, headers={"Content-Length": str(9*1024**2)}, content=b"{}")
    with pytest.raises(GatewayError) as error:
        asyncio.run(ExternalClient(settings, provider).request("test", b"png"))
    assert error.value.code == "EXTERNAL_RESPONSE_TOO_LARGE"
    before = len(calls)
    provider.readiness_url = None
    assert asyncio.run(ExternalClient(settings, provider).request("test"))["status"] == "configuration_valid"
    assert len(calls) == before


def test_json_request_and_escaped_secret_protection(settings, external):
    behavior, calls = external
    provider = get_provider(settings, "openthai")
    provider.request_format = "json_base64"
    asyncio.run(ExternalClient(settings, provider).request("test", b"png"))
    import base64
    assert json.loads(calls[0].content) == {"image": base64.b64encode(b"png").decode()}
    behavior["handler"] = lambda request: httpx.Response(200, content=b'{"text":"synthetic-provider-\\u0073ecret"}')
    with pytest.raises(GatewayError) as error:
        asyncio.run(ExternalClient(settings, provider).request("test", b"png"))
    assert error.value.code == "EXTERNAL_INVALID_RESPONSE"


def test_geometry_invalid_and_text_only_order(settings):
    from types import SimpleNamespace

    from app.services.global_layout_service import reading_lines
    with Image.new("RGB", (50, 50)) as image:
        crop = ImageService(settings).canonical_crop(image, None)
    provider = Provider(**REGISTRATION)
    for box in ([[1, 1], [3, 3]], [[1, 1], [1, 1], [1, 1], [1, 1]], [["x", 2]]*4):
        with pytest.raises(GatewayError):
            normalize_external({"data": {"text": "text", "lines": [{"text": "text", "box": box}]}}, provider, crop, None)
    run = SimpleNamespace(crop_stage="external_api", final_text="right\nleft", boxes=[{"text": "left", "bbox": [0, 0, 10, 10]}])
    assert reading_lines(run) == ["right", "left"]
