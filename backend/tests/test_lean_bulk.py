import json
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.db.models import (
    AppLog,
    Document,
    GlobalField,
    Metric,
    OCRErrorEvent,
    OCRField,
    PipelineRun,
)
from app.db.models import TestCase as Case
from app.services.field_service import compact_comparison, compare_field
from app.services.log_service import LogService
from app.services.test_case_service import TestCaseService as CaseService
from tests.test_global_layout import layout


def dynamic_rec(client):
    model = next(m for m in client.get("/api/pipelines/models").json() if m["kind"] == "rec")
    r = client.post(
        "/api/pipelines",
        json={
            "name": "Lean test",
            "source": model["source"],
            "execution_mode": "rec",
            "rec_model_id": model["id"],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["pipeline_id"]


def test_fresh_catalog_and_disabled_logs(client, caplog):
    with client.app.state.database.session_factory() as s:
        for model in [
            Document,
            Case,
            GlobalField,
            PipelineRun,
            OCRField,
            Metric,
            AppLog,
            OCRErrorEvent,
        ]:
            assert s.scalar(select(func.count()).select_from(model)) == 0
        logs = LogService(s, client.app.state.settings)
        logs.add("document_uploaded")
        run = PipelineRun(
            pipeline_id="safe", pipeline_name="safe", error_code="ERROR", request_id="safe_request"
        )
        logs.add("ocr_run_error", run=run)
        s.commit()
        assert s.scalar(select(func.count()).select_from(AppLog)) == 0
    assert "event=ocr_run_error" in caplog.text
    assert "test-gateway-secret" not in caplog.text
    assert client.get("/api/logs").json() == {"enabled": False, "total": 0, "items": []}


@pytest.mark.parametrize("whole", [False, True])
def test_compact_global_and_requested_detail(client, document, gateway, whole):
    from tests.test_benchmark_pipeline import parts

    def response(request):
        count = sum(key == "images" for key, _ in parts(request))
        return httpx.Response(
            200,
            json={
                "data": {
                    "count": count,
                    "results": [{"text": "Synthetic OCR", "confidence": 0.9} for _ in range(count)],
                },
                "meta": {"request_id": "synthetic-rec", "duration_ms": 10},
            },
        )

    gateway[0]["handler"] = response
    case, fields = layout(client, document)
    pid = dynamic_rec(client)
    root = "/api/test-cases/" + case["id"]
    response = client.post(root + "/run", json={"pipelines": [pid]})
    assert response.status_code == 200, response.text
    result = response.json()["runs"][0]
    assert result["fields"][0]["diagnostics"]["boxes"] is not None
    for f in fields:
        client.put(
            root + f"/global-fields/{f['id']}/ground-truth",
            json={"ground_truth_raw": "Synthetic GT"},
        )
    if whole:
        client.put(root + "/ground-truth", json={"ground_truth_raw": "Synthetic GT\nSynthetic GT"})
    response = client.post(
        root + "/evaluate",
        json={
            "mode": "whole_document" if whole else "per_field",
            "global_field_ids": [] if whole else [f["id"] for f in fields],
        },
    )
    assert response.status_code == 200, response.text
    detail = client.get(root).json()["runs"][0]
    evaluation = detail["document_evaluation"] if whole else detail["fields"][0]["evaluation"]
    assert evaluation["events"] and evaluation["spans"]
    with client.app.state.database.session_factory() as s:
        run = s.get(PipelineRun, result["id"])
        assert not run.raw_response or set(run.raw_response) == {"composition", "timing"}
        timing = run.raw_response["timing"]
        assert set(timing) == {"semantics", "wall_time_ms", "run_wall_time_ms", "total_field_compute_ms"}
        assert timing["semantics"] == "wall_clock_v1"
        assert all(isinstance(timing[k], int) for k in timing if k != "semantics")
        assert "global_fields" not in (run.raw_response or {})
        for f in run.fields:
            assert not {"raw_response", "raw_text", "reading_lines"} & f.diagnostics.keys()
        saved = run.document_evaluation if whole else run.fields[0].evaluation
        assert (
            not {
                "events",
                "spans",
                "prediction",
                "ground_truth_raw",
                "normalized_ocr",
                "normalized_ground_truth",
            }
            & saved.keys()
        )
        assert saved["character_edits"] >= 0
        assert s.scalar(select(func.count()).select_from(OCRErrorEvent)) == 0
        assert s.scalar(select(func.count()).select_from(AppLog)) == 0
    assert client.get("/api/analytics/errors").json()["items"]
    history = client.get("/api/history").json()[0]["runs"][0]
    e = history["document_evaluation"] if whole else history["fields"][0]["evaluation"]
    assert "spans" not in e


@pytest.mark.parametrize(
    "prediction,truth", [("abc", "ax"), ("", "ก"), ("ก\r\n ข", "ก ข"), ("same", "same")]
)
def test_compact_metrics_match_alignment(prediction, truth):
    full, small = compare_field(prediction, truth), compact_comparison(prediction, truth)
    assert all(full[k] == v for k, v in small.items())
    assert len(json.dumps(small)) < len(json.dumps(full))


@pytest.mark.parametrize("count", [1, 4, 200])
def test_bulk_delete_cascade_and_unrelated(client, document, count):
    with client.app.state.database.session_factory() as s:
        cases = [Case(document_id=document["id"], workflow="legacy") for _ in range(count + 1)]
        for c in cases:
            c.runs.append(
                PipelineRun(
                    pipeline_id="snapshot",
                    pipeline_name="snapshot",
                    status="success",
                    fields=[OCRField(field_index=1, ocr_text="safe", geometry={})],
                    metric_records=[Metric(text_kind="final", cer=0, wer=0, exact_match=True)],
                )
            )
        s.add_all(cases)
        s.commit()
        ids = [c.id for c in cases]
    request = ids[:-1] if count == 200 else [*ids[:-1], ids[0], str(uuid4())]
    r = client.post("/api/test-cases/bulk-delete", json={"test_case_ids": request})
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == count
    assert client.get("/api/test-cases/" + ids[-1]).status_code == 200
    with client.app.state.database.session_factory() as s:
        assert s.get(Document, document["id"])
        assert s.scalar(select(func.count()).select_from(PipelineRun)) == 1
        assert s.scalar(select(func.count()).select_from(OCRField)) == 1
        assert s.scalar(select(func.count()).select_from(Metric)) == 1


def test_bulk_delete_rollback(client, document, monkeypatch):
    from sqlalchemy.orm import Session

    with client.app.state.database.session_factory() as s:
        c = Case(document_id=document["id"])
        s.add(c)
        s.commit()
        cid = c.id

    def fail(self):
        raise RuntimeError("injected commit failure")

    with monkeypatch.context() as m:
        m.setattr(Session, "commit", fail)
        response = client.post("/api/test-cases/bulk-delete", json={"test_case_ids": [cid]},
                               headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 500
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert "injected commit failure" not in response.text
    assert client.get("/api/test-cases/" + cid).status_code == 200


def test_bulk_lock_limits_and_soft_exclusion(client, document):
    case, fields = layout(client, document)
    with client.app.state.database.session_factory() as s:
        c = s.get(Case, case["id"])
        c.ground_truth_raw = "Confirmed synthetic"
        c.status = "confirmed"
        f = s.get(GlobalField, fields[0]["id"])
        f.ground_truth_raw = "Confirmed synthetic"
        s.commit()
    ids = {
        "test_case_ids": [case["id"], case["id"]],
        "global_field_ids": [fields[0]["id"], fields[0]["id"], str(uuid4())],
    }
    a = client.post("/api/dataset/items/bulk-exclude", json=ids)
    assert a.status_code == 200, a.text
    assert a.json() == {"requested": 3, "excluded": 2, "already_excluded": 0, "not_found": 1}
    assert client.post("/api/dataset/items/bulk-exclude", json=ids).json()["already_excluded"] == 2
    saved = client.get("/api/test-cases/" + case["id"]).json()
    assert saved["ground_truth_raw"] == "Confirmed synthetic"
    assert saved["global_fields"][0]["ground_truth_raw"] == "Confirmed synthetic"
    assert client.get("/api/documents/" + document["id"]).status_code == 200
    assert client.get("/api/dataset/samples").json()["total"] == 0
    for path in ["/api/test-cases/bulk-delete", "/api/dataset/items/bulk-exclude"]:
        assert (
            client.post(
                path, json={"test_case_ids": [str(uuid4()) for _ in range(201)]}
            ).status_code
            == 422
        )
        assert client.post(path, json={"test_case_ids": []}).status_code == 422
    # Both deletion routes share the application's OCR mutex.
    import inspect

    from app.api.routes.test_cases import bulk_delete, delete_test_case

    assert "ocr_lock" in inspect.getsource(bulk_delete) and "ocr_lock" in inspect.getsource(
        delete_test_case
    )


def test_legacy_errors_on_demand_no_rows(client, document):
    with client.app.state.database.session_factory() as s:
        c = Case(document_id=document["id"], ground_truth_raw="abc", status="confirmed")
        r = PipelineRun(
            pipeline_id="retired",
            pipeline_name="retired",
            status="success",
            final_text="ax",
            raw_text=None,
        )
        c.runs.append(r)
        s.add(c)
        s.flush()
        CaseService.evaluate(r, "abc")
        s.commit()
        assert s.scalar(select(func.count()).select_from(OCRErrorEvent)) == 0
        assert r.metric_records[0].cer == r.metric_records[1].cer
    data = client.get("/api/analytics/errors").json()
    assert data["total"] > 0


def test_list_consumers_never_hydrate_alignment(client, document, monkeypatch):
    with client.app.state.database.session_factory() as s:
        c = Case(document_id=document["id"], ground_truth_raw="abc", status="confirmed")
        run = PipelineRun(
            pipeline_id="snapshot", pipeline_name="snapshot", status="success", final_text="ax"
        )
        c.runs.append(run)
        s.add(c)
        s.flush()
        CaseService.evaluate(run, "abc")
        s.commit()

    def forbidden(*args, **kwargs):
        raise AssertionError("Alignment must be explicitly requested")

    monkeypatch.setattr("app.services.serializers.compare_field", forbidden)
    monkeypatch.setattr("app.repositories.error_repository.error_breakdown", forbidden)
    for path in [
        "/api/history",
        "/api/test-cases",
        "/api/dataset/samples",
        "/api/analytics/comparison",
    ]:
        response = client.get(path)
        assert response.status_code == 200, response.text


def test_bulk_exclusion_rollback_and_combined_limit(client, document, monkeypatch):
    from sqlalchemy.orm import Session

    case, fields = layout(client, document)
    body = {"test_case_ids": [case["id"]], "global_field_ids": [fields[0]["id"]]}

    def fail(self):
        raise RuntimeError("injected commit failure")

    with monkeypatch.context() as m:
        m.setattr(Session, "commit", fail)
        response = client.post("/api/dataset/items/bulk-exclude", json=body,
                               headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 500
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    with client.app.state.database.session_factory() as s:
        assert s.get(Case, case["id"]).dataset_excluded_at is None
        assert s.get(GlobalField, fields[0]["id"]).dataset_excluded_at is None
    assert (
        client.post(
            "/api/dataset/items/bulk-exclude",
            json={
                "test_case_ids": [str(uuid4()) for _ in range(100)],
                "global_field_ids": [str(uuid4()) for _ in range(101)],
            },
        ).status_code
        == 422
    )


def test_model_provenance_is_allowlisted():
    from app.services.lean_storage import compact_provenance

    response = {
        "data": {"results": [{"text": "discard"}]},
        "meta": {"request_id": "discard"},
        "composition": {
            "recognition": {
                "id": "model-id",
                "name": "V6",
                "version": "6",
                "weight": "thai_ft_v2",
                "model_dir": "private-path",
                "raw_output": ["discard"],
            }
        },
    }
    assert compact_provenance(response) == {
        "composition": {
            "recognition": {"id": "model-id", "name": "V6", "version": "6", "weight": "thai_ft_v2"}
        }
    }


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="local PostgreSQL required")
def test_postgresql_clean_head_and_bulk_fk_cascades(settings):
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session

    from alembic import command
    from app.core.config import BACKEND_ROOT
    from app.db.seed import seed_database
    from app.services.dataset_service import DatasetService

    url = make_url(os.environ["TEST_DATABASE_URL"])
    assert url.host in {"127.0.0.1", "localhost"} and url.database.endswith("_test")
    schema = "lean_" + uuid4().hex
    engine = create_engine(url)
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(f"CREATE SCHEMA {schema}")
        with engine.connect() as conn:
            conn.exec_driver_sql(f"SET search_path TO {schema}")
            conn.commit()
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
            assert (
                conn.scalar(text("SELECT version_num FROM alembic_version"))
                == "0013_external_providers"
            )
            previous = conn.dialect.default_schema_name
            conn.dialect.default_schema_name = schema
            try:
                command.check(cfg)
            finally:
                conn.dialect.default_schema_name = previous
            conn.commit()
            with Session(conn) as s:
                seed_database(s, settings)
                d = Document(
                    filename="synthetic.png",
                    storage_key="synthetic.png",
                    mime_type="image/png",
                    width=50,
                    height=50,
                )
                deleted, retained = Case(document=d), Case(document=d)
                deleted.runs.append(
                    PipelineRun(
                        pipeline_id="synthetic",
                        pipeline_name="synthetic",
                        status="success",
                        fields=[OCRField(field_index=1, geometry={}, ocr_text="synthetic")],
                        metric_records=[Metric(text_kind="final", cer=0, wer=0, exact_match=True)],
                    )
                )
                s.add_all([deleted, retained])
                s.commit()
                deleted_id, retained_id, document_id = deleted.id, retained.id, d.id
                service = CaseService(s, settings, None)
                assert service.bulk_delete([deleted_id])["deleted"] == 1
                s.expire_all()
                assert s.get(Document, document_id) and s.get(Case, retained_id)
                for model in [PipelineRun, OCRField, Metric, AppLog, OCRErrorEvent]:
                    assert s.scalar(select(func.count()).select_from(model)) == 0
                assert DatasetService(service).bulk_exclude([retained_id], [])["excluded"] == 1
                assert s.get(Case, retained_id).dataset_excluded_at is not None
                s.commit()
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        engine.dispose()
