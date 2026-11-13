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


EXACT_TEXT = "ไทย English\r\nSecond\u2028row\n\n"
EXACT_LINES = [
    {"text": "right", "confidence": 0.95, "row": 0, "box": [[40, 1], [70, 1], [70, 10], [40, 10]]},
    {"text": "left", "confidence": None, "row": 0, "box": [[1, 1], [30, 1], [30, 10], [1, 10]]},
]


def openthai_data(**changes):
    data = {"text": EXACT_TEXT, "lines": deepcopy(EXACT_LINES), "confidence": None,
            "geometry_available": True, "image": {"width": 80, "height": 60}, "rotation": 0, "text_angle": 0}
    data.update(changes)
    return data


def openthai_envelope(data, service="openthai2-ocr-text"):
    return {"data": data, "meta": {"request_id": "req_synthetic_contract", "api_version": "v1", "service": service,
                                    "duration_ms": 12}}


def batch_envelope(result, **counters):
    item = {"index": counters.pop("index", 0), "status": counters.pop("status", "success"),
            "result": result, "error": counters.pop("error", None)}
    data = {"results": [item], "total": 1, "succeeded": 1, "failed": 0}
    data.update(counters)
    return openthai_envelope(data)


def sample_crop(settings):
    with Image.new("RGB", (100, 100)) as image:
        return ImageService(settings).canonical_crop(image, {"x1": 10, "y1": 20, "x2": 90, "y2": 80})


def test_single_and_gateway_envelopes_preserve_text_geometry_and_null_confidence(settings):
    crop, provider, roi = sample_crop(settings), Provider(**REGISTRATION), {"x1": 10, "y1": 20}
    for service in ("openthai2-ocr-text", "model-api-gateway"):
        payload = openthai_envelope(openthai_data(), service)
        original = deepcopy(payload)
        text, score, boxes, meta = normalize_external(payload, provider, crop, roi)
        assert text == EXACT_TEXT and score is None and payload == original
        assert meta["service"] == service
        assert boxes[0]["text"] == "right" and boxes[0]["confidence"] == 0.95
        assert boxes[0]["crop_polygon"][0] == [40, 1] and boxes[0]["polygon"][0] == [50, 21]
        assert boxes[1]["text"] == "left" and boxes[1]["confidence"] is None
        assert boxes[1]["polygon"][0] == [11, 21]


def test_one_image_batch_envelope_uses_matching_item_once(settings):
    crop, provider = sample_crop(settings), Provider(**REGISTRATION)
    payload = batch_envelope(openthai_data())
    text, score, boxes, _ = normalize_external(payload, provider, crop, {"x1": 10, "y1": 20})
    assert text == EXACT_TEXT and score is None
    assert [box["polygon"][0] for box in boxes] == [[50, 21], [11, 21]]
    assert boxes[0]["crop_bbox"] == [40, 1, 70, 10]


def test_batch_count_index_and_failed_items_are_not_successful_text(settings):
    crop, provider = sample_crop(settings), Provider(**REGISTRATION)
    partial = openthai_envelope({"results": [
        {"index": 0, "status": "success", "result": openthai_data(), "error": None},
        {"index": 1, "status": "error", "result": None, "error": {"code": "INVALID_IMAGE", "message": "The uploaded image is invalid."}},
    ], "total": 2, "succeeded": 1, "failed": 1})
    wrong_index = batch_envelope(openthai_data(), index=1)
    failed = batch_envelope(None, status="error", error={"code": "INVALID_IMAGE", "message": "The uploaded image is invalid."},
                            succeeded=0, failed=1)
    hidden = batch_envelope(openthai_data(text="do-not-keep"), status="error",
                            error={"code": "INVALID_IMAGE", "message": "The uploaded image is invalid."}, succeeded=0, failed=1)
    leaf = openthai_envelope({"contract_version": "leaf-inference-v1", "kind": "text_recognition_batch", "count": 1,
                              "results": [{"rec_text": "อย่าใช้", "rec_score": 0.4}]})
    wrapped = {"data": openthai_envelope(openthai_data()), "meta": {"request_id": "outer"}}
    cases = (
        (partial, "Batch result count does not match input images"),
        (wrong_index, "Batch result index does not match the input image"),
        (failed, "OpenThai batch item failed: INVALID_IMAGE"),
        (hidden, "OpenThai batch item is not a successful OCR result"),
        (leaf, "OpenThai response is not a single text result or a batch item"),
        (wrapped, "OpenThai response text is missing or not a string"),
        (openthai_envelope({}), "OpenThai response text is missing or not a string"),
    )
    for payload, message in cases:
        with pytest.raises(GatewayError) as error:
            normalize_external(payload, provider, crop, None)
        assert error.value.code == "INVALID_OCR_RESPONSE" and str(error.value) == message
        assert "อย่าใช้" not in str(error.value) and "do-not-keep" not in str(error.value)


def test_invalid_text_geometry_dimensions_and_line_limit(settings):
    crop, provider = sample_crop(settings), Provider(**REGISTRATION)
    too_long = openthai_envelope(openthai_data(text="ก" * 32769, lines=[]))
    missing_line = openthai_envelope(openthai_data(lines=[{"text": None, "box": [[1, 1], [2, 1], [2, 2], [1, 2]]}]))
    bad_frame = openthai_envelope(openthai_data(image={"width": 79, "height": 60}))
    too_many = openthai_envelope(openthai_data(lines=[{"text": "a"} for _ in range(129)]))
    many = openthai_envelope(openthai_data(text="a\n" * 127 + "a", lines=[{"text": "a"} for _ in range(128)]))
    with pytest.raises(GatewayError) as error:
        normalize_external(too_long, provider, crop, None)
    assert error.value.code == "INVALID_OCR_RESPONSE"
    with pytest.raises(GatewayError) as error:
        normalize_external(missing_line, provider, crop, None)
    assert error.value.code == "INVALID_OCR_RESPONSE"
    for payload, message in (
        (bad_frame, "External image coordinate frame mismatch"),
        (too_many, "External lines exceed contract limits"),
        (openthai_envelope(openthai_data(lines=[{"text": "a", "box": [[1, 1], [2, 2]]}])), "External geometry is invalid"),
    ):
        with pytest.raises(GatewayError) as error:
            normalize_external(payload, provider, crop, None)
        assert error.value.code == "EXTERNAL_INVALID_RESPONSE" and message in str(error.value)
    assert normalize_external(many, provider, crop, None)[0] == "a\n" * 127 + "a"


def test_sync_run_keeps_model_order_and_labels_it(client, document, external):
    behavior, _calls = external
    case, _fields = layout(client, document, count=1, prefill=False)
    behavior["handler"] = lambda request: httpx.Response(200, json=batch_envelope(openthai_data(
        image={"width": 190, "height": 100})))
    pipeline_id = client.post("/api/pipelines", json=definition()).json()["pipeline_id"]
    response = client.post(f"/api/test-cases/{case['id']}/run", json={"pipelines": [pipeline_id]})
    assert response.status_code == 200, response.text
    run = response.json()["runs"][0]
    field = run["fields"][0]
    assert run["final_text"] == field["ocr_text"] == EXACT_TEXT
    assert run["confidence"] is None and field["confidence"] is None
    assert field["diagnostics"]["ordering"] == "model_reading_order"
    boxes = field["diagnostics"]["boxes"]
    assert [box["text"] for box in boxes] == ["right", "left"]
    assert boxes[0]["polygon"][0] == [50, 21] and boxes[0]["crop_polygon"][0] == [40, 1]


def test_batch_result_persists_exact_text_boxes_and_replay(client, document, external):
    behavior, calls = external
    case, fields = layout(client, document, count=1, prefill=False)
    behavior["handler"] = lambda request: httpx.Response(200, json=batch_envelope(openthai_data(
        image={"width": 190, "height": 100})))
    pipeline_id = client.post("/api/pipelines", json=definition()).json()["pipeline_id"]
    job = submit(client, case, [pipeline_id], "openthai-batch-contract")
    final = wait_job(client, job["job_id"])
    assert final["status"] == "completed" and final["completed_units"] == 1 and final["failed_units"] == 0
    results = client.get(f"/api/ocr-jobs/{job['job_id']}/results").json()
    run = results["runs"][0]
    field = run["fields"][0]
    assert run["status"] == "success" and run["final_text"] == EXACT_TEXT and run["confidence"] is None
    assert field["status"] == "success" and field["ocr_text"] == EXACT_TEXT and field["confidence"] is None
    boxes = field["diagnostics"]["boxes"]
    assert [box["text"] for box in boxes] == ["right", "left"]
    assert boxes[0]["polygon"][0] == [50, 21]
    assert boxes[0]["crop_polygon"][0] == [40, 1] and boxes[1]["confidence"] is None
    assert field["diagnostics"]["ordering"] == "model_reading_order"
    assert submit(client, case, [pipeline_id], "openthai-batch-contract")["job_id"] == job["job_id"]
    assert len(calls) == 1
    again = client.get(f"/api/ocr-jobs/{job['job_id']}/results").json()["runs"][0]["fields"][0]
    assert again["ocr_text"] == field["ocr_text"] and again["diagnostics"]["boxes"] == boxes
    assert again["diagnostics"]["ordering"] == "model_reading_order"
    assert fields[0]["roi"] == {"x1": 10, "y1": 20, "x2": 200, "y2": 120}


def test_failed_batch_item_stays_failed_without_manufactured_text(client, document, external):
    behavior, calls = external
    case, _ = layout(client, document, count=1, prefill=False)
    behavior["handler"] = lambda request: httpx.Response(200, json=batch_envelope(
        None, status="error", error={"code": "INVALID_IMAGE", "message": "The uploaded image is invalid."},
        succeeded=0, failed=1))
    pipeline_id = client.post("/api/pipelines", json=definition()).json()["pipeline_id"]
    job = submit(client, case, [pipeline_id], "openthai-batch-failure")
    final = wait_job(client, job["job_id"])
    assert final["status"] == "failed" and final["failed_units"] == 1 and final["progress_percent"] == 100
    run = client.get(f"/api/ocr-jobs/{job['job_id']}/results").json()["runs"][0]
    field = run["fields"][0]
    assert run["status"] == "error" and run["error_code"] == "FIELD_PIPELINE_ERROR"
    assert field["status"] == "error" and field["ocr_text"] == ""
    assert field["diagnostics"]["error_code"] == "INVALID_OCR_RESPONSE"
    assert field["diagnostics"]["failure_stage"] == "gateway_contract" and field["diagnostics"]["http_status"] is None
    assert field["diagnostics"]["ordering"] == "model_reading_order"
    assert "INVALID_IMAGE" in field["diagnostics"]["error_message"]
    assert submit(client, case, [pipeline_id], "openthai-batch-failure")["job_id"] == job["job_id"]
    assert len(calls) == 1
