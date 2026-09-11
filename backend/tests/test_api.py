import io
import json

import httpx
import pytest
from PIL import Image
from sqlalchemy import inspect

from app.db.models import Base
from app.services.image_service import ImageService
from tests.test_gateway_and_fairness import envelope

PIPELINES = ["mint", "hutch_crop", "hutch_full"]


def run(client, case, pipelines=PIPELINES):
    response = client.post(f"/api/test-cases/{case['id']}/run", json={"pipelines": pipelines})
    assert response.status_code == 200, response.text
    return response.json()["runs"]


def test_health_and_migration(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["database"]["status"] == "connected"
    database = client.app.state.database
    database.migrate()  # Repeated startup is idempotent.
    inspector = inspect(database.engine)
    for table in Base.metadata.sorted_tables:
        assert {col.name for col in table.columns} == {
            col["name"] for col in inspector.get_columns(table.name)
        }


def test_upload_storage_and_hash(client, document, png):
    assert len(document["sha256"]) == 64
    assert document["width"] == 300
    response = client.get(document["image_url"])
    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"]
    assert Image.open(io.BytesIO(response.content)).size == (300, 200)
    assert "base64" not in json.dumps(document)


@pytest.mark.parametrize(
    "content,mime,expected",
    [(b"bad", "image/png", 415), (b"", "image/png", 400), (b"bad", "text/plain", 415)],
)
def test_bad_uploads(client, content, mime, expected):
    assert (
        client.post("/api/documents", files={"file": ("bad.png", content, mime)}).status_code
        == expected
    )


def test_mime_size_and_dimensions(client, png, settings):
    assert (
        client.post("/api/documents", files={"file": ("wrong.jpg", png, "image/jpeg")}).status_code
        == 415
    )
    settings.max_upload_mb = 1
    assert (
        client.post(
            "/api/documents", files={"file": ("large.png", b"x" * (1024 * 1024 + 1), "image/png")}
        ).status_code
        == 413
    )
    settings.max_image_dimension = 100
    assert (
        client.post("/api/documents", files={"file": ("wide.png", png, "image/png")}).status_code
        == 413
    )


@pytest.mark.parametrize(
    "roi",
    [
        {"x1": -1, "y1": 0, "x2": 20, "y2": 20},
        {"x1": 0, "y1": 0, "x2": 301, "y2": 20},
        {"x1": 20, "y1": 0, "x2": 20, "y2": 20},
        {"x1": 1.2, "y1": 0, "x2": 20, "y2": 20},
    ],
)
def test_roi_validation(client, document, roi):
    assert (
        client.post("/api/test-cases", json={"document_id": document["id"], "roi": roi}).status_code
        == 422
    )


def test_http_fixture_workflow_and_metrics_update(client, case):
    runs = run(client, case)
    assert [item["status"] for item in runs] == ["success", "success", "success"]
    assert runs[2]["status"] == "success"
    assert all("is_mock" not in item for item in runs)
    assert len({item["crop_sha256"] for item in runs[:2]}) == 1
    assert runs[0]["metrics"]["cer"] == 0
    assert runs[2]["metrics"] is not None
    original_prediction = runs[0]["final_text"]
    updated = client.put(
        f"/api/test-cases/{case['id']}/ground-truth",
        json={"ground_truth_raw": "different", "confirmed": True},
    ).json()
    assert updated["status"] == "confirmed"
    assert updated["runs"][0]["final_text"] == original_prediction
    assert updated["runs"][0]["metrics"]["cer"] > 0
    assert updated["runs"][0]["raw_metrics"] is not None
    assert len(client.get(f"/api/test-cases/{case['id']}/results").json()["runs"]) == 3
    assert len(client.get("/api/history").json()) == 1


def test_no_ground_truth_and_empty_ground_truth(client, document):
    case = client.post("/api/test-cases", json={"document_id": document["id"]}).json()
    runs = run(client, case)
    assert all(item["metrics"] is None for item in runs)
    updated = client.put(
        f"/api/test-cases/{case['id']}/ground-truth",
        json={"ground_truth_raw": "", "confirmed": True},
    ).json()
    assert updated["runs"][0]["metrics"] == {"cer": None, "wer": None, "exact_match": False}


def test_matrix_latest_runs_filters_and_categories(client, case, document):
    run(client, case)
    run(client, case)
    rows = client.get(
        "/api/matrix", params={"category": "thai_text", "document": document["id"]}
    ).json()
    assert len(rows) == 3
    assert all(row["tests"] == 1 for row in rows)
    assert rows[0]["cer"] == 0
    assert rows[0]["avg_gateway_time_ms"] == 123.4
    assert all(
        row["tests"] == 0 for row in client.get("/api/matrix", params={"category": "blur"}).json()
    )
    assert len(client.get("/api/matrix", params={"pipeline": "mint"}).json()) == 1
    category = client.get("/api/analytics/categories", params={"category": "stamp"}).json()[0]
    assert category["test_cases"] == 1
    assert category["pipelines"][0]["tests"] == 1
    assert client.get("/api/history", params={"date_from": "2100-01-01"}).json() == []


def test_failure_isolation_real_mode_and_trace(client, case, gateway):
    behavior, _ = gateway

    def handler(request):
        if request.url.params["engine"] == "custom":
            return httpx.Response(
                503,
                json={
                    "error": {
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "test-gateway-secret",
                        "request_id": "mint-failed",
                    }
                },
            )
        return httpx.Response(200, json=envelope("paddle"))

    behavior["handler"] = handler
    runs = run(client, case)
    assert [item["status"] for item in runs] == ["error", "success", "success"]
    assert all("is_mock" not in item for item in runs)
    assert runs[0]["gateway_request_id"] == "mint-failed"
    assert "test-gateway-secret" not in json.dumps(runs)
    assert runs[1]["gateway_duration_ms"] == 123.4
    assert all(item["input_sha256"] for item in runs)


def test_config_validation_and_secret_status(client):
    assert all(item["api_key_configured"] for item in client.get("/api/pipelines").json())
    for values in (
        {"base_url": "file:///etc/passwd"},
        {"base_url": "https://user:secret@example.com"},
        {"endpoint": "//other.example/ocr"},
        {"query_params": {"api_key": "secret"}},
        {"engine": "paddle"},
        {"include_roi": True},
        {"file_field_name": "file"},
    ):
        assert client.put("/api/pipelines/mint", json=values).status_code == 422
    assert "test-gateway-secret" not in client.get("/api/pipelines").text
    assert client.post("/api/pipelines/mint/test-connection").json()["status"] == "available"


def test_roi_changes_preserve_old_predictions(client, case):
    run(client, case)
    assert client.put(f"/api/test-cases/{case['id']}/roi", json={"roi": None}).status_code == 409
    assert (
        client.put(
            f"/api/test-cases/{case['id']}/categories", json={"category_codes": ["blur"]}
        ).status_code
        == 200
    )


def test_gateway_partial_status_and_auth(client, gateway):
    behavior, _ = gateway
    behavior["handler"] = lambda request: httpx.Response(
        200,
        json={
            "data": {
                "services": [
                    {"name": "ocr-custom", "status": "ready"},
                    {"name": "ocr-paddle", "status": "not_ready"},
                    {"name": "layout", "status": "ready"},
                ]
            },
            "meta": {},
        },
    )
    status = client.get("/api/integrations/model-gateway/status").json()
    assert (
        status["mint"] == "available"
        and status["hutch_crop"] == "unavailable"
        and status["hutch_full"] == "unavailable"
    )
    assert status["auto_roi"] == "available"
    behavior["handler"] = lambda request: httpx.Response(
        401, json={"error": {"code": "AUTHENTICATION_REQUIRED"}}
    )
    assert (
        client.get("/api/integrations/model-gateway/status").json()["mint"] == "not_authenticated"
    )


def test_auto_roi_and_failure_do_not_block_manual(client, case, document, gateway):
    behavior, calls = gateway
    behavior["handler"] = lambda request: httpx.Response(
        200,
        json={
            "data": {
                "regions": [
                    {"bbox": [10.4, 20.2, 290.9, 99.1], "score": 0.8, "source": "text-detection"}
                ]
            },
            "meta": {"request_id": "layout-id"},
        },
    )
    result = client.post(f"/api/documents/{document['id']}/auto-rois", json={}).json()
    assert result["regions"][0]["roi"] == {"x1": 10, "y1": 20, "x2": 291, "y2": 100}
    assert calls[-1].url.path == "/api/v1/document-layouts"
    from tests.test_gateway_and_fairness import multipart

    assert multipart(calls[-1])["expand_text_rois"] == b"false"
    behavior["handler"] = lambda request: httpx.Response(
        503, json={"error": {"code": "UNAVAILABLE"}}
    )
    assert client.post(f"/api/documents/{document['id']}/auto-rois", json={}).status_code == 503
    from tests.upstream_fixture import response
    behavior["handler"] = response
    assert [item["status"] for item in run(client, case)] == ["success", "success", "success"]


def test_crop_is_deterministic(settings, png):
    image = ImageService.open(png)
    roi = {"x1": 0, "y1": 0, "x2": 300, "y2": 200}
    images = ImageService(settings)
    assert images.canonical_crop(image, roi) == images.canonical_crop(image, None)
