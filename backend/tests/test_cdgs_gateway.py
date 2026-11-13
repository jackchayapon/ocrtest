import asyncio
import json
import logging
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app.integrations.gateway_routes import resolve_endpoint
from app.integrations.model_gateway import GatewayError, ModelGatewayClient
from app.pipelines.dynamic import model_request
from app.schemas.dynamic_pipelines import OCRModelInput


@pytest.mark.parametrize(
    "base,path,expected",
    [
        ("https://gateway.example", "/api/v1/ocr-results", "/api/v1/ocr-results"),
        ("https://gateway.example/api/v1", "/api/v1/ocr-results", "/api/v1/ocr-results"),
        (
            "https://gateway.example/paddle/api/v1/",
            "/api/v1/ocr-results",
            "/paddle/api/v1/ocr-results",
        ),
        ("https://gateway.example/paddle", "/api/v1/ocr-results", "/paddle/api/v1/ocr-results"),
        (
            "https://gateway.example/api/v1",
            "/paddle/api/v1/ocr-results",
            "/paddle/api/v1/ocr-results",
        ),
        (
            "https://gateway.example/paddle/api/v1",
            "/paddle/api/v1/text-recognition-batches?version=6&model=thai_ft_v2",
            "/paddle/api/v1/text-recognition-batches?version=6&model=thai_ft_v2",
        ),
        ("https://gateway.example/tenant/api/v1", "/api/v1/health", "/tenant/api/v1/health"),
    ],
)
def test_prefix_resolution(base, path, expected):
    assert resolve_endpoint(base, path) == "https://gateway.example" + expected


@pytest.mark.parametrize(
    "path",
    [
        "https://other.example/api/v1/ocr-results",
        "//other.example/api/v1/health",
        "/api/v1/../ocr",
        "/api/v1/%252e%252e/ocr",
        "/api/v1/%5cocr",
        "/api//v1/ocr",
        "/api/v1/ocr#secret",
        "/api/v1/paddle/api/v1/ocr",
        "/paddle/paddle/api/v1/ocr",
        "/api/v1/ocr\n",
    ],
)
def test_unsafe_or_duplicate_routes_rejected(path):
    with pytest.raises(ValueError):
        resolve_endpoint("https://gateway.example/api/v1", path)


def test_independent_prefixes_and_legacy_database_paths(settings, png):
    settings.model_gateway_base_url = "https://gateway.example/api/v1"
    settings.model_gateway_service_prefixes = {
        "paddle": "/paddle/api/v1",
        "status": "/paddle/api/v1",
    }
    client = ModelGatewayClient(settings)

    def request(engine):
        return client.build_request(
            png=png,
            endpoint="/api/v1/ocr-results",
            query_params={"engine": engine},
            fields={},
            request_id="route-test",
        )

    assert request("paddle")["url"] == "https://gateway.example/paddle/api/v1/ocr-results"
    assert request("custom")["url"] == "https://gateway.example/api/v1/ocr-results"
    assert client.resolve_endpoint("/api/v1/layout-predictions", "layout").endswith(
        "/api/v1/layout-predictions"
    )
    batch = client.build_batch_request(
        pngs=[png, png], endpoint="/api/v1/text-detection-batches", version=6, request_id="det"
    )
    assert batch["params"] == {"version": "6"}
    assert batch["url"] == "https://gateway.example/api/v1/text-detection-batches"
    assert [part[1][1] for part in batch["files"]] == [png, png]


@pytest.mark.parametrize("base", ["https://gateway.example/paddle", "https://gateway.example/paddle/api/v1"])
@pytest.mark.parametrize("path", ["/api/v1/layout-predictions", "/paddle/api/v1/layout-predictions"])
def test_layout_predictions_use_layout_prefix_once(settings, png, base, path):
    settings.model_gateway_base_url = base
    settings.model_gateway_service_prefixes = {"layout": "/paddle/api/v1", "det_rec": "/rec/api/v1"}
    client = ModelGatewayClient(settings)
    request = client.build_request(png=png, endpoint=path, query_params={},
                                   fields={"auto_roi_mode": "text-line", "expand_text_rois": False},
                                   request_id="layout-route")
    assert request["url"] == "https://gateway.example/paddle/api/v1/layout-predictions"
    assert client.service_for(request["url"], {}) == "layout"
    assert set(request["files"]) == {"image"}
    assert request["files"]["image"][1] == png
    assert request["data"] == {"auto_roi_mode": "text-line", "expand_text_rois": "false"}


def test_layout_predictions_honor_independent_or_disabled_service(settings, png):
    settings.model_gateway_base_url = "https://gateway.example/paddle"
    settings.model_gateway_service_prefixes = {"layout": "/layout/api/v1", "det_rec": "/rec/api/v1"}
    client = ModelGatewayClient(settings)
    arguments = dict(png=png, endpoint="/api/v1/layout-predictions", query_params={}, fields={}, request_id="layout")
    assert client.build_request(**arguments)["url"] == "https://gateway.example/layout/api/v1/layout-predictions"
    settings.model_gateway_service_prefixes["layout"] = None
    with pytest.raises(GatewayError) as error:
        client.build_request(**arguments)
    assert error.value.code == "GATEWAY_SERVICE_UNAVAILABLE"


@pytest.mark.parametrize(
    "prefix",
    [
        "https://other.example/api/v1",
        "/paddle/api/v1?key=bad",
        "/../api/v1",
        "/api/v1/paddle/api/v1",
    ],
)
def test_service_prefix_cannot_change_origin(prefix):
    with pytest.raises(ValueError):
        resolve_endpoint(
            "https://gateway.example/api/v1", "/api/v1/ocr-results", {"paddle": prefix}, "paddle"
        )


def test_prefixed_model_path_validates_without_rewriting():
    path = "/paddle/api/v1/text-recognition-batches?version=6&model=thai_ft_v2"
    model = OCRModelInput(
        name="REC", kind="rec", source="official", version="6", weight="thai_ft_v2", batch_path=path
    )
    assert model.batch_path == path


@pytest.mark.parametrize(
    "status,category",
    [
        (401, "authentication"),
        (403, "authorization"),
        (404, "route_not_found"),
        (422, "request_contract"),
        (503, "upstream"),
        (302, "gateway"),
    ],
)
def test_http_failure_logs_are_safe(settings, png, gateway, caplog, status, category):
    gateway[0]["handler"] = lambda request: httpx.Response(
        status,
        headers={"location": "https://other.example/"},
        text="test-gateway-secret private OCR text",
    )
    client = ModelGatewayClient(settings, pipeline_id="official")
    request = client.build_request(
        png=png,
        endpoint="/api/v1/ocr-results",
        query_params={"engine": "paddle"},
        fields={},
        request_id="safe-id",
    )
    with caplog.at_level(logging.INFO), pytest.raises(GatewayError) as error:
        asyncio.run(client.send(request))
    assert error.value.http_status == status
    event = json.loads(caplog.records[-1].message)
    assert event["failure_category"] == category
    assert event["http_status"] == status and event["pipeline_id"] == "official"
    assert event["request_id"] == "safe-id" and event["duration_ms"] >= 0
    assert "test-gateway-secret" not in caplog.text and "private OCR text" not in caplog.text
    assert len(gateway[1]) == 1


def test_key_whitespace_and_foreign_send_are_safe(settings, png, gateway):
    settings.model_gateway_api_key = SecretStr(" test-gateway-secret \n")
    client = ModelGatewayClient(settings)
    request = client.build_request(
        png=png, endpoint="/api/v1/ocr-results", query_params={}, fields={}, request_id="id"
    )
    assert request["headers"]["Authorization"] == "Bearer test-gateway-secret"
    request["url"] = "https://other.example/api/v1/ocr-results"
    with pytest.raises(GatewayError) as error:
        asyncio.run(client.send(request))
    assert error.value.code == "INVALID_GATEWAY_ROUTE" and not gateway[1]


def test_status_uses_its_own_prefix(settings, gateway):
    settings.model_gateway_base_url = "https://gateway.example/api/v1"
    settings.model_gateway_service_prefixes = {"status": "/paddle/api/v1"}
    gateway[0]["handler"] = lambda request: httpx.Response(
        200, json={"data": {"services": []}, "meta": {}}
    )
    asyncio.run(ModelGatewayClient(settings).status())
    assert [r.url.path for r in gateway[1]] == ["/paddle/api/v1/health", "/paddle/api/v1/readiness"]


@pytest.mark.parametrize("version,variant", [("5", None), ("6", "thai_ft_v2")])
def test_dynamic_model_query_is_preserved(settings, png, version, variant):
    settings.model_gateway_base_url = "https://gateway.example/api/v1"
    settings.model_gateway_service_prefixes = {"det_rec": "/paddle/api/v1"}
    query = "version=" + version + ("&model=" + variant if variant else "")
    model = SimpleNamespace(batch_path="/api/v1/text-recognition-batches?" + query, version=version)
    request = model_request(ModelGatewayClient(settings), model, [png], "rec-id")
    assert request["url"] == "https://gateway.example/paddle/api/v1/text-recognition-batches"
    assert request["params"] == {"version": version, **({"model": variant} if variant else {})}


@pytest.mark.parametrize("service", ["paddle", "custom"])
def test_null_service_never_sends_inference(settings, png, gateway, service):
    settings.model_gateway_service_prefixes = {service: None}
    client = ModelGatewayClient(settings)
    with pytest.raises(GatewayError) as error:
        client.build_request(
            png=png,
            endpoint="/api/v1/ocr-results",
            query_params={"engine": service},
            fields={},
            request_id="blocked",
        )
    assert error.value.code == "GATEWAY_SERVICE_UNAVAILABLE"
    assert not gateway[1]


@pytest.mark.parametrize("ready", [False, True])
@pytest.mark.parametrize("engine,name", [("paddle", "ocr-paddle"), ("custom", "ocr-custom")])
def test_paddle_base_only_checks_readiness_before_integrated(
    settings, png, gateway, ready, engine, name
):
    settings.model_gateway_base_url = "https://gateway.example/paddle"

    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": {"services": [{"name": name, "status": "ready" if ready else "not_ready"}]},
                "meta": {},
            },
        )

    gateway[0]["handler"] = handler
    client = ModelGatewayClient(settings)
    request = client.build_request(
        png=png,
        endpoint="/api/v1/ocr-results",
        query_params={"engine": engine},
        fields={},
        request_id="gated",
    )
    if ready:
        asyncio.run(client.send(request))
    else:
        with pytest.raises(GatewayError) as error:
            asyncio.run(client.send(request))
        assert error.value.code == "GATEWAY_SERVICE_UNAVAILABLE"
    assert len([r for r in gateway[1] if r.method == "POST"]) == int(ready)
    assert all(r.url.path.startswith("/paddle/api/v1/") for r in gateway[1])


def test_disabled_dynamic_integrated_connection_is_unavailable(client, settings, gateway):
    settings.model_gateway_service_prefixes = {"paddle": None, "custom": None}
    gateway[0]["handler"] = lambda request: httpx.Response(
        200, json={"data": {"services": [{"name": "ocr-paddle", "status": "ready"}]}, "meta": {}}
    )
    pipeline = client.post(
        "/api/pipelines",
        json={"name": "Unavailable official", "source": "official", "execution_mode": "integrated"},
    ).json()
    response = client.post("/api/pipelines/" + pipeline["pipeline_id"] + "/test-connection")
    assert response.json()["status"] == "unavailable"
    assert not any(r.method == "POST" for r in gateway[1])


def test_service_inventory_does_not_claim_variant_readiness(settings, gateway):
    services = [
        {"name": name, "status": "ready" if name != "table-model" else "not_ready"}
        for name in ["text-detection", "text-recognition", "layout-model", "layout", "table-model"]
    ]
    gateway[0]["handler"] = lambda request: httpx.Response(
        200, json={"data": {"services": services}, "meta": {}}
    )
    result = asyncio.run(ModelGatewayClient(settings).status())
    assert result["services"] == {
        "det": "available",
        "rec": "available",
        "layout_leaf": "available",
        "layout_pipeline": "available",
        "table_v2": "unavailable",
    }
    assert result["thai_ft_v2"] == "unknown"


@pytest.mark.parametrize("source,service", [("official", "paddle"), ("custom", "custom")])
def test_blocked_integrated_run_preserves_case_and_makes_no_upstream_post(
    client, case, settings, gateway, source, service
):
    settings.model_gateway_service_prefixes = {service: None}
    pipeline = client.post(
        "/api/pipelines",
        json={"name": "Disabled integrated", "source": source, "execution_mode": "integrated"},
    ).json()
    response = client.post(
        f"/api/test-cases/{case['id']}/run", json={"pipelines": [pipeline["pipeline_id"]]}
    )
    assert response.status_code == 200
    run = response.json()["runs"][0]
    assert run["status"] == "error" and run["error_code"] == "GATEWAY_SERVICE_UNAVAILABLE"
    assert not any(r.method == "POST" for r in gateway[1])
    assert client.get(f"/api/test-cases/{case['id']}").status_code == 200
