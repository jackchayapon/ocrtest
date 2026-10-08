"""Traffic optimizations must preserve the current API and fresh OCR configuration."""

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from threading import Event

import pytest
from sqlalchemy import select

from app.db.diagnostics import ReadStats, current_stats, install_diagnostics
from app.db.models import GlobalField, Metric, OCRField, PipelineConfig, PipelineRun
from app.db.models import TestCase as Case
from app.repositories.benchmark_repository import BenchmarkRepository
from app.services.config_cache import ConfigCache
from app.services.field_service import compact_comparison
from tests.test_dynamic_pipelines import integrated, model


@contextmanager
def measured():
    stats = ReadStats()
    token = current_stats.set(stats)
    try:
        yield stats
    finally:
        current_stats.reset(token)


@pytest.fixture
def traffic_cases(client, case):
    with client.app.state.database.session_factory() as session:
        original = session.get(Case, case["id"])
        original.status = "confirmed"
        configs = [
            PipelineConfig(
                pipeline_id="traffic_" + str(i),
                name="Synthetic " + str(i),
                execution_mode="integrated",
                source="custom",
                enabled=True,
                integrated_options={
                    "version": "6",
                    "det_weight": "baseline",
                    "rec_weight": "baseline",
                },
            )
            for i in range(2)
        ]
        session.add_all(configs)
        cases = [
            original,
            Case(
                document_id=original.document_id,
                workflow="global",
                status="tested",
                evaluation_mode="per_field",
            ),
            Case(
                document_id=original.document_id,
                workflow="global",
                status="tested",
                evaluation_mode="whole_document",
                ground_truth_raw="Synthetic GT",
                document_gt_confirmed_at=datetime.now(timezone.utc),
            ),
        ]
        session.add_all(cases)
        session.flush()
        for c in cases:
            global_field = None
            if c.workflow == "global":
                global_field = GlobalField(
                    test_case_id=c.id,
                    field_index=0,
                    roi={"x1": 1, "y1": 1, "x2": 50, "y2": 30},
                    source="manual",
                    ground_truth_raw="Synthetic GT",
                    confirmed_at=datetime.now(timezone.utc),
                )
                c.global_fields.append(global_field)
                session.flush()
            for p in configs:
                run = PipelineRun(
                    pipeline_id=p.pipeline_id,
                    pipeline_name=p.name,
                    status="success",
                    raw_text="Synthetic OCR",
                    final_text="Synthetic OCR",
                    normalized_text="Synthetic OCR",
                    confidence=0.9,
                    processing_time_ms=1200,
                    gateway_duration_ms=1000,
                    crop_stage="global_fields" if global_field else "app_crop",
                    boxes=[{"text": "Synthetic OCR", "bbox": [1, 1, 50, 30]}] * 30,
                    raw_response={"synthetic_legacy": "x" * 2000},
                    document_evaluation={"cer": 0.1, "evaluated_at": "2026-10-01T00:00:00+00:00"},
                )
                run.metric_records = [
                    Metric(text_kind="final", cer=0.1, wer=0.2, exact_match=False)
                ]
                run.fields = [
                    OCRField(
                        field_index=0,
                        global_field_id=global_field.id if global_field else None,
                        geometry={"bbox": [1, 1, 50, 30]},
                        ocr_text="Synthetic OCR",
                        ground_truth_raw="Synthetic GT",
                        ground_truth_normalized="Synthetic GT",
                        confirmed_at=datetime.now(timezone.utc),
                        evaluation=compact_comparison("Synthetic OCR", "Synthetic GT"),
                        diagnostics={"legacy": "y" * 3000},
                    )
                ]
                c.runs.append(run)
        session.commit()
        return [c.id for c in cases]


@pytest.mark.parametrize(
    "path", ["/api/pipelines", "/api/pipelines/models", "/api/categories", "/api/document-types"]
)
def test_catalog_hits_have_no_sql_or_checkout(client, path):
    install_diagnostics(client.app.state.database.engine)
    first = client.get(path)
    with measured() as stats:
        second = client.get(path)
    assert first.json() == second.json()
    assert stats.queries == stats.checkouts == 0
    assert stats.cache_hits == 1
    assert "test-gateway-secret" not in second.text


def test_create_edit_delete_invalidate_after_commit(client):
    assert client.get("/api/pipelines").json() == []
    p = client.post("/api/pipelines", json=integrated()).json()
    assert client.get("/api/pipelines").json()[0]["name"] == p["name"]
    assert (
        client.put(
            "/api/pipelines/" + p["pipeline_id"] + "/definition", json=integrated(name="Changed")
        ).status_code
        == 200
    )
    assert client.get("/api/pipelines").json()[0]["name"] == "Changed"
    assert (
        client.put(
            "/api/pipelines/" + p["pipeline_id"] + "/definition",
            json=integrated(name="Changed", enabled=False),
        ).status_code
        == 200
    )
    assert not client.get("/api/pipelines").json()[0]["enabled"]
    assert client.delete("/api/pipelines/" + p["pipeline_id"]).status_code == 204
    assert client.get("/api/pipelines").json() == []


def test_model_edit_invalidates_embedded_pipeline_catalog_and_execution(client, case, gateway):
    m = client.post("/api/pipelines/models", json=model()).json()
    p = client.post(
        "/api/pipelines",
        json={"name": "REC", "source": "custom", "execution_mode": "rec", "rec_model_id": m["id"]},
    ).json()
    client.get("/api/pipelines")
    client.get("/api/pipelines/models")
    changed = model(
        name="Updated REC",
        version="6",
        single_path="/api/v1/text-recognitions?version=6&model=thai_ft_v2",
        batch_path="/api/v1/text-recognition-batches?version=6&model=thai_ft_v2",
    )
    assert client.put("/api/pipelines/models/" + m["id"], json=changed).status_code == 200
    assert client.get("/api/pipelines").json()[0]["rec_model"]["name"] == "Updated REC"
    assert any(v["name"] == "Updated REC" for v in client.get("/api/pipelines/models").json())
    run = client.post(
        "/api/test-cases/" + case["id"] + "/run", json={"pipelines": [p["pipeline_id"]]}
    )
    assert run.status_code == 200
    assert gateway[1][-1].url.params["version"] == "6"


def test_document_type_invalidation_and_failed_mutation(client):
    before = client.get("/api/document-types").json()
    created = client.post("/api/document-types", json={"name": "Traffic Synthetic"}).json()
    assert len(client.get("/api/document-types").json()) == len(before) + 1
    assert client.delete("/api/document-types/" + created["id"]).status_code == 200
    assert client.get("/api/document-types").json() == before
    assert client.post("/api/pipelines", json={"name": "Invalid"}).status_code == 422
    assert client.get("/api/pipelines").json() == []


def test_rollback_does_not_invalidate_or_leak_uncommitted_catalog(client):
    p = client.post("/api/pipelines", json=integrated()).json()
    original = client.get("/api/pipelines").json()
    with client.app.state.database.session_factory() as s:
        record = s.scalar(
            select(PipelineConfig).where(PipelineConfig.pipeline_id == p["pipeline_id"])
        )
        record.name = "Uncommitted"
        s.flush()
        s.rollback()
    assert client.get("/api/pipelines").json() == original
    assert client.get("/api/pipelines?fresh=true").json() == original


def test_other_worker_is_bounded_and_explicit_fresh_reads_are_immediate(client):
    # Independent caches represent workers sharing the same database/session factory.
    other = ConfigCache(clock=lambda: clock[0])
    clock = [0]
    app_cache = client.app.state.config_cache
    client.app.state.config_cache = other
    assert client.get("/api/pipelines").json() == []
    client.app.state.config_cache = app_cache
    p = client.post("/api/pipelines", json=integrated()).json()
    client.app.state.config_cache = other
    assert client.get("/api/pipelines").json() == []
    clock[0] = 61
    assert client.get("/api/pipelines").json()[0]["pipeline_id"] == p["pipeline_id"]
    client.app.state.config_cache = app_cache
    client.put(
        "/api/pipelines/" + p["pipeline_id"] + "/definition",
        json=integrated(name="New worker value"),
    )
    client.app.state.config_cache = other
    assert client.get("/api/pipelines?fresh=true").json()[0]["name"] == "New worker value"
    client.app.state.config_cache = app_cache


def test_cache_single_flight_defensive_copy_and_failure_retry():
    cache = ConfigCache()
    started, release = Event(), Event()
    calls = []

    def load():
        calls.append(1)
        started.set()
        assert release.wait(5)
        return [{"value": 1}]

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(cache.get, "pipelines", load) for _ in range(8)]
        assert started.wait(5)
        release.set()
        values = [f.result() for f in futures]
    assert len(calls) == 1
    values[0][0]["value"] = 2
    assert cache.get("pipelines", load) == [{"value": 1}]
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cache.get("failure", lambda: (_ for _ in ()).throw(RuntimeError("synthetic")))


def test_history_summary_matches_full_except_explicit_details_and_preserves_pagination(
    client, traffic_cases
):
    install_diagnostics(client.app.state.database.engine)
    with measured() as full_stats:
        full = client.get("/api/history?limit=2").json()
    with measured() as compact_stats:
        compact = client.get("/api/history?limit=2&view=summary").json()
    expected = deepcopy(full)
    for c in expected:
        for run in c["runs"]:
            run.update(boxes=[], raw_response=None)
            for field in run["fields"]:
                field["diagnostics"] = None
    assert compact == expected
    assert compact_stats.queries == full_stats.queries
    assert compact_stats.estimated_result_bytes < full_stats.estimated_result_bytes
    second = client.get("/api/history?limit=2&offset=2&view=summary").json()
    assert len(second) == 1
    assert not {r["id"] for r in compact} & {r["id"] for r in second}
    detail = client.get("/api/test-cases/" + compact[0]["id"]).json()
    assert detail["runs"][0]["boxes"] and detail["runs"][0]["fields"][0]["diagnostics"]


@pytest.mark.parametrize(
    "endpoint",
    [
        "/matrix",
        "/analytics/summary",
        "/analytics/pipelines",
        "/analytics/categories",
        "/analytics/document-types",
        "/analytics/comparison",
        "/analytics/errors",
    ],
)
def test_analytics_projection_equals_fully_loaded_reference(
    client, traffic_cases, monkeypatch, endpoint
):
    install_diagnostics(client.app.state.database.engine)
    with measured() as optimized_stats:
        optimized = client.get("/api" + endpoint).json()
    original_cases, original_configs = BenchmarkRepository.cases, BenchmarkRepository.configs

    def full_cases(self, *args, **kwargs):
        kwargs.update(analytics=False, texts=False)
        return original_cases(self, *args, **kwargs)

    def full_configs(self, **kwargs):
        return original_configs(self, summary=False)

    with monkeypatch.context() as patch:
        patch.setattr(BenchmarkRepository, "cases", full_cases)
        patch.setattr(BenchmarkRepository, "configs", full_configs)
        with measured() as original_stats:
            reference = client.get("/api" + endpoint).json()
    if isinstance(optimized, dict):
        optimized.pop("computation_ms", None)
        reference.pop("computation_ms", None)
    assert optimized == reference
    assert optimized_stats.estimated_result_bytes <= original_stats.estimated_result_bytes
    assert optimized_stats.queries <= original_stats.queries


def test_diagnostics_logs_only_low_cardinality_numbers_and_cors(client, caplog):
    from app.db.diagnostics import log_stats

    with caplog.at_level("INFO", logger="app.db.diagnostics"):
        log_stats("/api/test-cases/{case_id}", 200, ReadStats(queries=2, rows=3))
    data = json.loads(caplog.records[-1].message.removeprefix("db_read "))
    assert data["queries"] == 2 and data["rows"] == 3
    assert set(data) == {
        "route",
        "status",
        "queries",
        "query_ms",
        "rows",
        "estimated_result_bytes",
        "checkouts",
        "connections",
        "cache_hits",
        "cache_misses",
    }
    response = client.options(
        "/api/pipelines",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_pool_reconnect_after_dispose(client):
    first = client.get("/api/pipelines/models?fresh=true").json()
    client.app.state.database.engine.dispose()
    assert client.get("/api/pipelines/models?fresh=true").json() == first


def test_invalidation_during_slow_load_never_blocks_commit_or_repopulates_old_value():
    cache = ConfigCache()
    started, release = Event(), Event()

    def old_load():
        started.set()
        assert release.wait(5)
        return "old"

    with ThreadPoolExecutor(max_workers=2) as pool:
        old = pool.submit(cache.get, "pipelines", old_load)
        assert started.wait(5)
        invalidation = pool.submit(cache.invalidate, "pipelines")
        invalidation.result(timeout=2)
        assert cache.get("pipelines", lambda: "new") == "new"
        release.set()
        assert old.result() == "old"
    assert cache.get("pipelines", lambda: "wrong") == "new"


def test_single_case_error_filter_is_pushed_to_sql_without_changing_results(
    client, traffic_cases, monkeypatch
):
    install_diagnostics(client.app.state.database.engine)
    path = "/api/analytics/errors?test_case_id=" + traffic_cases[0]
    with measured() as optimized:
        actual = client.get(path).json()
    cases = BenchmarkRepository.cases

    def whole_cohort(self, *args, **kwargs):
        kwargs.pop("test_case_id", None)
        return cases(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(BenchmarkRepository, "cases", whole_cohort)
        with measured() as previous:
            expected = client.get(path).json()
    assert actual == expected
    assert optimized.rows < previous.rows
    assert optimized.estimated_result_bytes < previous.estimated_result_bytes


def test_opt_in_diagnostics_capture_requests_without_sql_text_or_secret_values(
    settings, gateway, caplog
):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with caplog.at_level("INFO", logger="app.db.diagnostics"):
        with TestClient(create_app(settings.model_copy(update={"db_diagnostics": True}))) as client:
            assert client.get("/api/pipelines/models").status_code == 200
            assert client.get("/api/pipelines/models").status_code == 200
    records = [
        json.loads(r.message.removeprefix("db_read "))
        for r in caplog.records
        if r.name == "app.db.diagnostics"
    ]
    assert len(records) == 2
    assert records[0]["queries"] == 1 and records[1]["queries"] == 0
    assert records[1]["cache_hits"] == 1
    assert all(r["route"] == "/pipelines/models" for r in records)
    assert "test-gateway-secret" not in caplog.text
    assert "SELECT" not in caplog.text and "INSERT" not in caplog.text
