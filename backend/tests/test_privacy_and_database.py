import io
import json
import os

import httpx
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from alembic import command
from app.core.config import BACKEND_ROOT, Settings
from app.db.models import PipelineRun
from app.main import create_app
from tests.test_gateway_and_fairness import envelope


def test_private_upstream_fields_never_reach_storage_or_frontend(client, case, gateway, caplog):
    behavior, _ = gateway
    payload = envelope("custom")
    payload["data"].update(
        {
            "api_key": "test-gateway-secret",
            "input_img": [[1, 2, 3]],
            "nested": {"image_base64": "SGVsbG8=", "echo": "test-gateway-secret"},
        }
    )
    behavior["handler"] = lambda request: httpx.Response(200, json=payload)
    response = client.post(f"/api/test-cases/{case['id']}/run", json={"pipelines": ["mint"]})
    assert response.status_code == 200
    assert "test-gateway-secret" not in response.text
    assert "SGVsbG8=" not in response.text
    assert response.json()["runs"][0]["status"] == "success"
    with client.app.state.database.session_factory() as session:
        stored = session.scalar(select(PipelineRun)).raw_response
        assert stored["data"]["input_img"] == "[redacted]"
        assert "test-gateway-secret" not in json.dumps(stored)
    assert "บริษัท" not in caplog.text
    assert "test-gateway-secret" not in caplog.text
    assert not list(client.app.state.storage.root.glob("*.tmp"))


def test_bad_metadata_cannot_cancel_other_runs(client, case, gateway):
    behavior, _ = gateway
    payload = envelope("custom")
    payload["meta"]["service"] = {"unexpected": "object"}
    payload["meta"]["model"] = "x" * 5000
    behavior["handler"] = lambda request: httpx.Response(200, json=payload)
    response = client.post(
        f"/api/test-cases/{case['id']}/run",
        json={"pipelines": ["mint", "hutch_crop", "hutch_full"]},
    )
    assert response.status_code == 200
    assert [run["status"] for run in response.json()["runs"]] == ["success", "success", "success"]
    assert response.json()["runs"][0]["gateway_service"] is None


def test_postgresql_migration_sql_and_driver(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://migration_check:unused@localhost/test")
    settings = Settings(_env_file=None)
    assert settings.sqlalchemy_url.startswith("postgresql+psycopg://")
    stream = io.StringIO()
    config = Config(str(BACKEND_ROOT / "alembic.ini"), output_buffer=stream)
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(config, "head", sql=True)
    sql = stream.getvalue()
    for required in (
        "UUID",
        "JSONB",
        "crop_sha256",
        "gateway_request_id",
        "gateway_duration_ms",
        "query_params",
    ):
        assert required in sql
    assert "unused@" not in sql


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL to a disposable PostgreSQL/Neon database",
)
def test_live_postgresql_repository_roundtrip(tmp_path, png, gateway):
    settings = Settings(
        _env_file=None,
        database_url=os.environ["TEST_DATABASE_URL"],
        storage_path=tmp_path / "pg-uploads",
        model_gateway_api_key="test-gateway-secret",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["database"]["provider"] == "postgresql"
        document = client.post(
            "/api/documents", files={"file": ("pg-fixture.png", png, "image/png")}
        ).json()
        case = client.post(
            "/api/test-cases",
            json={
                "document_id": document["id"],
                "ground_truth_raw": "บริษัท ซีดีจี จำกัด",
                "category_codes": ["thai_text"],
            },
        ).json()
        for pipeline_id in ("mint", "hutch_crop", "hutch_full"):
            client.put(f"/api/pipelines/{pipeline_id}", json={"enabled": True})
        response = client.post(
            f"/api/test-cases/{case['id']}/run",
            json={"pipelines": ["mint", "hutch_crop", "hutch_full"]},
        )
        assert response.status_code == 200
        assert len(response.json()["runs"]) == 3
        assert len({run["crop_sha256"] for run in response.json()["runs"][:2]}) == 1
        assert response.json()["runs"][2]["status"] == "success"
        assert (
            client.get("/api/matrix", params={"document": document["id"]}).json()[0]["tests"] == 1
        )
