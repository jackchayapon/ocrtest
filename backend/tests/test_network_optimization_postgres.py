"""Current dynamic workflow on a newly created, isolated PostgreSQL database."""

import io
import os
from uuid import uuid4
from zipfile import ZipFile

import psycopg
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.main import create_app
from tests.test_dynamic_pipelines import integrated


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="Disposable local PostgreSQL required"
)
def test_current_postgresql_upload_ocr_gt_history_metrics_dataset_and_reconnect(
    tmp_path, png, gateway
):
    source = make_url(os.environ["TEST_DATABASE_URL"])
    assert source.host in {"127.0.0.1", "localhost"} and source.database.endswith("_test")
    name = "network_flow_" + uuid4().hex + "_test"
    with psycopg.connect(
        source.set(drivername="postgresql", database="postgres").render_as_string(
            hide_password=False
        ),
        autocommit=True,
    ) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    app = create_app(
        Settings(
            _env_file=None,
            database_url=source.set(database=name).render_as_string(hide_password=False),
            storage_path=tmp_path / "uploads",
            model_gateway_base_url="https://synthetic.invalid",
            model_gateway_api_key="test-only-key",
        )
    )
    with TestClient(app) as client:
        assert client.get("/api/health").json()["database"]["provider"] == "postgresql"
        pipeline = client.post("/api/pipelines", json=integrated(source="official")).json()
        doc = client.post(
            "/api/documents", files={"file": ("synthetic.png", png, "image/png")}
        ).json()
        roi = {"x1": 40, "y1": 30, "x2": 270, "y2": 150}
        case = client.post(
            "/api/test-cases", json={"document_id": doc["id"], "roi": roi, "roi_source": "manual"}
        ).json()
        root = "/api/test-cases/" + case["id"]
        response = client.post(root + "/run", json={"pipelines": [pipeline["pipeline_id"]]})
        assert response.status_code == 200, response.text
        assert response.json()["runs"][0]["status"] == "success"
        # Labels are confirmed GT, never the upstream prediction or numeric metrics.
        confirmed = client.put(
            root + "/ground-truth",
            json={"ground_truth_raw": "Synthetic confirmed GT", "confirmed": True},
        )
        assert confirmed.status_code == 200
        full, compact = client.get(root).json(), client.get("/api/history?view=summary").json()
        assert any(c["id"] == case["id"] for c in compact)
        assert full["runs"][0]["metrics"]["cer"] is not None
        matrix = client.get("/api/matrix?document=" + doc["id"]).json()
        assert matrix[0]["tests"] == matrix[0]["evaluated_runs"] == 1
        assert client.get("/api/analytics/errors?test_case_id=" + case["id"]).status_code == 200
        samples = client.get("/api/dataset/samples?document=" + doc["id"]).json()
        assert samples["total"] == 1
        export = client.post("/api/dataset/export", json={"test_case_ids": [case["id"]]})
        assert export.status_code == 200
        with ZipFile(io.BytesIO(export.content)) as archive:
            assert archive.testzip() is None
            assert (
                archive.read("dataset/label.txt").decode("utf-8")
                == "images/000001.png\tSynthetic confirmed GT\n"
            )
            crop = Image.open(io.BytesIO(archive.read("dataset/images/000001.png")))
            assert crop.size == (230, 120)
            expected_crop = Image.open(io.BytesIO(png)).crop((40, 30, 270, 150)).convert("RGB")
            assert crop.convert("RGB").tobytes() == expected_crop.tobytes()
        # Separate app/session factories model workers sharing ONLY the database.
        worker = create_app(app.state.settings)
        with TestClient(worker) as other:
            cached = other.get("/api/pipelines").json()[0]
            definition = integrated(source="custom", name="Worker current", version="5", rec_weight="thai_ft_v2")
            assert client.put("/api/pipelines/" + pipeline["pipeline_id"] + "/definition", json=definition).status_code == 200
            # Ordinary cross-worker catalog reads are bounded stale, not silently
            # assumed globally invalidated; explicit fresh must read the commit.
            assert other.get("/api/pipelines").json()[0]["name"] == cached["name"]
            gateway[1].clear()
            response = other.post(root + "/run", json={"pipelines": [pipeline["pipeline_id"]]})
            assert response.json()["runs"][0]["status"] == "success"
            assert dict(gateway[1][-1].url.params) == dict(engine="custom", version="5", det_model="baseline", rec_model="thai_ft_v2")
            assert other.get("/api/pipelines?fresh=true").json()[0]["name"] == "Worker current"
            assert client.put("/api/pipelines/" + pipeline["pipeline_id"] + "/definition", json={**definition, "name": "After expiry"}).status_code == 200
            clock = worker.state.config_cache.clock
            worker.state.config_cache.clock = lambda: clock() + 61
            assert other.get("/api/pipelines").json()[0]["name"] == "After expiry"
        # Reconnect and repeat reads; no replacement SQLite or production credentials.
        with app.state.database.engine.connect() as connection:
            backend_pid = connection.scalar(text("SELECT pg_backend_pid()"))
        with psycopg.connect(
            source.set(drivername="postgresql", database=name).render_as_string(
                hide_password=False
            ),
            autocommit=True,
        ) as connection:
            connection.execute("SELECT pg_terminate_backend(%s)", (backend_pid,))
        # pool_pre_ping must reconnect this killed, idle connection automatically.
        assert client.get(root).json()["ground_truth_raw"] == "Synthetic confirmed GT"
        with app.state.database.session_factory() as session:
            assert (
                session.scalar(text("SELECT version_num FROM alembic_version"))
                == "0010_dynamic_pipelines"
            )
