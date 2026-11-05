import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError

from app.db.models import OCRField, OCRJob, PipelineRun, now
from app.services.ocr_jobs import Checkpoint, JobWorker, LostLease, enqueue
from app.services.test_case_service import TestCaseService as CaseService
from tests.test_dynamic_pipelines import integrated
from tests.test_global_layout import layout


def pipeline(client):
    response = client.post("/api/pipelines", json=integrated())
    assert response.status_code == 201, response.text
    return response.json()["pipeline_id"]


def wait_job(client, job_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = client.get(f"/api/ocr-jobs/{job_id}")
        assert response.status_code == 200, response.text
        value = response.json()
        if value["status"] not in ("queued", "running"):
            return value
        time.sleep(0.05)
    pytest.fail("Job did not finish")


def submit(client, case, ids, key=None):
    response = client.post(
        f"/api/test-cases/{case['id']}/jobs",
        json={
            "pipelines": ids,
            "idempotency_key": key or str(uuid4()),
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_job_global_completion_results_and_gt(client, document):
    case, fields = layout(client, document)
    pid = pipeline(client)
    job = submit(client, case, [pid])
    final = wait_job(client, job["job_id"])
    assert final["status"] == "completed", final
    assert (final["completed_units"], final["failed_units"], final["progress_percent"]) == (
        2,
        0,
        100,
    )
    result = client.get(f"/api/ocr-jobs/{job['job_id']}/results").json()
    assert len(result["runs"]) == 1
    assert {f["global_field_id"] for f in result["runs"][0]["fields"]} == {f["id"] for f in fields}
    assert client.get(f"/api/test-cases/{case['id']}/jobs").json()["job_id"] == job["job_id"]
    root = f"/api/test-cases/{case['id']}"
    assert (
        client.put(
            root + f"/global-fields/{fields[0]['id']}/ground-truth",
            json={"ground_truth_raw": "ABC"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            root + "/evaluate", json={"mode": "per_field", "global_field_ids": [fields[0]["id"]]}
        ).status_code
        == 200
    )


def test_legacy_job_completion(client, case):
    job = submit(client, case, [pipeline(client)])
    final = wait_job(client, job["job_id"])
    assert final["status"] == "completed", final
    assert final["completed_units"] == 1
    assert len(client.get(f"/api/ocr-jobs/{job['job_id']}/results").json()["runs"]) == 1


def test_idempotency_after_completion_no_duplicate_history(client, case, gateway):
    ids = [pipeline(client)]
    job = submit(client, case, ids, "same-request")
    wait_job(client, job["job_id"])
    count = len(gateway[1])
    again = submit(client, case, ids, "same-request")
    assert again["job_id"] == job["job_id"]
    assert len(gateway[1]) == count
    assert len(client.get(f"/api/test-cases/{case['id']}").json()["runs"]) == 1
    other = pipeline(client)
    assert (
        client.post(
            f"/api/test-cases/{case['id']}/jobs",
            json={"pipelines": [other], "idempotency_key": "same-request"},
        ).status_code
        == 409
    )


@pytest.mark.parametrize("code", [422, 503])
def test_partial_failure_and_no_retry_422(client, document, gateway, code):
    case, _ = layout(client, document)
    ids = [pipeline(client), pipeline(client)]
    behavior, calls = gateway
    original = behavior["handler"]
    inference = 0

    def handler(request):
        nonlocal inference
        if request.method == "POST":
            inference += 1
            if inference == 1:
                return httpx.Response(
                    code, json={"error": {"code": "MODEL_FAILURE", "message": "synthetic failure"}}
                )
        return original(request)

    behavior["handler"] = handler
    final = wait_job(client, submit(client, case, ids)["job_id"])
    assert final["status"] == "partial_success", final
    assert final["completed_units"] == 4 and final["failed_units"] == 1
    assert inference >= 4


def paused_worker(client):
    # Keep the application event consumer asleep; run claims explicitly in these tests.
    worker = client.app.state.job_worker

    def create(case, ids, key=None):
        with client.app.state.database.session_factory() as session:
            cases = CaseService(session, client.app.state.settings, client.app.state.storage)
            return enqueue(cases, case["id"], ids, key or str(uuid4())).id

    return worker, create


def test_active_case_dedupe_mutation_and_lease_fence(client, document):
    case, _ = layout(client, document)
    pid = pipeline(client)
    worker, create = paused_worker(client)
    jid = create(case, [pid])
    assert create(case, [pid]) == jid  # Separate tab/key still one active job.
    assert client.delete(f"/api/test-cases/{case['id']}").status_code == 409
    assert (
        client.put(
            f"/api/test-cases/{case['id']}/global-fields", json={"fields": [], "confirmed": False}
        ).status_code
        == 409
    )
    claimed, _ = worker.claim()
    assert claimed == jid
    rival = JobWorker(worker.database, worker.settings, worker.storage, asyncio.Lock())
    assert rival.claim()[0] is None
    with worker.database.session_factory() as session:
        job = session.get(OCRJob, jid)
        context = Checkpoint(session, job, "wrong-owner")
        with pytest.raises(LostLease):
            context.fence()


def test_expired_lease_recovery_and_config_snapshot(client, document):
    case, _ = layout(client, document)
    pid = pipeline(client)
    worker, create = paused_worker(client)
    jid = create(case, [pid])
    assert worker.claim()[0] == jid
    with worker.database.session_factory() as session:
        job = session.get(OCRJob, jid)
        job.lease_expires_at = now() - timedelta(seconds=1)
        session.commit()
    replacement = JobWorker(worker.database, worker.settings, worker.storage, asyncio.Lock())
    assert replacement.claim()[0] == jid
    asyncio.run(replacement.execute(jid))
    final = client.get(f"/api/ocr-jobs/{jid}").json()
    assert final["status"] == "completed", final
    assert final["attempt_count"] == 2
    with worker.database.session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PipelineRun)
                .where(PipelineRun.test_case_id == case["id"])
            )
            == 1
        )
        assert session.scalar(select(func.count()).select_from(OCRField)) == 2


def test_unknown_job_and_job_cors(client):
    url = f"/api/ocr-jobs/{uuid4()}"
    response = client.get(url, headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 404
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    preflight = client.options(
        f"/api/test-cases/{uuid4()}/jobs",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:3000"
    rejected = client.options(
        url, headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in rejected.headers


@pytest.mark.parametrize("interruption", ["process", "database"])
def test_interrupted_after_checkpoint_reuses_completed_units(
    client, document, gateway, monkeypatch, interruption
):
    # Ten fields force two bounded checkpoints at the unchanged field budget eight.
    case, fields = layout(client, document, count=10)
    pid = pipeline(client)
    worker, create = paused_worker(client)
    jid = create(case, [pid])
    assert worker.claim()[0] == jid
    original = Checkpoint.save

    def interrupt(self, parents, prefill=None):
        original(self, parents, prefill)
        if self.job.completed_units == 8:
            if interruption == "database":
                raise OperationalError("synthetic ambiguous commit", {}, Exception("synthetic"))
            raise asyncio.CancelledError()

    monkeypatch.setattr(Checkpoint, "save", interrupt)
    with pytest.raises(LostLease if interruption == "database" else asyncio.CancelledError):
        asyncio.run(worker.execute(jid))
    with worker.database.session_factory() as session:
        job = session.get(OCRJob, jid)
        assert job.completed_units == 8
        existing = set(session.scalars(select(OCRField.id)))
        assert len(existing) == 8
        job.lease_expires_at = now() - timedelta(seconds=1)
        session.commit()
    count = len(gateway[1])
    monkeypatch.setattr(Checkpoint, "save", original)
    replacement = JobWorker(worker.database, worker.settings, worker.storage, asyncio.Lock())
    assert replacement.claim()[0] == jid
    asyncio.run(replacement.execute(jid))
    final = client.get(f"/api/ocr-jobs/{jid}").json()
    assert final["status"] == "completed", final
    assert final["completed_units"] == 10
    with worker.database.session_factory() as session:
        all_ids = set(session.scalars(select(OCRField.id)))
        assert len(all_ids) == 10 and existing.issubset(all_ids)
        assert session.scalar(select(func.count()).select_from(PipelineRun)) == 1
    # No previously checkpointed integrated OCR calls are replayed.
    resumed = [c for c in gateway[1][count:] if c.url.path.endswith("ocr-results")]
    assert len(resumed) == 2


def test_failed_all_is_not_success_and_poll_has_no_private_snapshot(client, case, gateway):
    gateway[0]["handler"] = lambda request: httpx.Response(
        422, json={"error": {"code": "UPSTREAM_MODEL_ERROR"}}
    )
    final = wait_job(client, submit(client, case, [pipeline(client)])["job_id"])
    assert final["status"] == "failed" and final["failed_units"] == 1
    assert final["progress_percent"] == 100
    assert "config_snapshot" not in final and "lease_owner" not in final
    assert "test-gateway-secret" not in str(final)


def test_unexpected_failure_preserves_checkpoint_and_finalizes_parent(
    client, document, monkeypatch
):
    case, _ = layout(client, document, count=10)
    pid = pipeline(client)
    worker, create = paused_worker(client)
    jid = create(case, [pid])
    original = Checkpoint.save

    def fail_after_save(self, parents, prefill=None):
        original(self, parents, prefill)
        if self.job.completed_units == 8:
            raise RuntimeError("synthetic private error text must not escape")

    monkeypatch.setattr(Checkpoint, "save", fail_after_save)
    assert worker.claim()[0] == jid
    asyncio.run(worker.execute(jid))
    final = client.get(f"/api/ocr-jobs/{jid}").json()
    assert final["status"] == "failed" and final["completed_units"] == 8
    assert "synthetic private" not in str(final)
    saved = client.get(f"/api/ocr-jobs/{jid}/results").json()["runs"]
    assert len(saved) == 1 and saved[0]["status"] == "error" and len(saved[0]["fields"]) == 8


def test_missing_original_source_fails_without_fabrication(client, document):
    case, _ = layout(client, document)
    worker, create = paused_worker(client)
    jid = create(case, [pipeline(client)])
    with worker.database.session_factory() as session:
        from app.db.models import Document

        doc = session.get(Document, document["id"])
        worker.storage.delete(doc.storage_key)
    assert worker.claim()[0] == jid
    asyncio.run(worker.execute(jid))
    final = client.get(f"/api/ocr-jobs/{jid}").json()
    assert final["status"] == "failed" and final["completed_units"] == 0
    assert client.get(f"/api/ocr-jobs/{jid}/results").json()["runs"] == []


def test_job_enqueue_and_poll_do_not_fetch_history_or_snapshots(client, document):
    case, _ = layout(client, document)
    pid = pipeline(client)
    statements = []
    engine = client.app.state.database.engine

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        _, create = paused_worker(client)
        jid = create(case, [pid])
        assert not any(
            "pipeline_runs" in s or "ocr_fields" in s
            for s in statements
            if s.lstrip().startswith("select")
        )
        statements.clear()
        for _ in range(3):
            assert client.get(f"/api/ocr-jobs/{jid}").status_code == 200
        selects = [s for s in statements if s.lstrip().startswith("select")]
        assert len(selects) == 3
        assert all("config_snapshot" not in s and "prefill_results" not in s for s in selects)
    finally:
        event.remove(engine, "before_cursor_execute", capture)


@pytest.mark.parametrize("count", [1, 50])
def test_bulk_job_guard_has_constant_query_budget(client, document, count):
    from app.db.models import TestCase as Case

    with client.app.state.database.session_factory() as session:
        cases = [Case(document_id=document["id"], workflow="legacy") for _ in range(count)]
        session.add_all(cases)
        session.commit()
        ids = [c.id for c in cases]
    statements = []
    engine = client.app.state.database.engine

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lower().lstrip().startswith("select") and "ocr_jobs" in statement.lower():
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.post("/api/test-cases/bulk-delete", json={"test_case_ids": ids})
        assert response.status_code == 200 and response.json()["deleted"] == count
        assert len(statements) <= 2
    finally:
        event.remove(engine, "before_cursor_execute", capture)


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Isolated local PostgreSQL required")
def test_postgresql_additive_migration_atomic_claim_and_recovery(tmp_path, png, gateway):
    import psycopg
    from alembic.config import Config
    from fastapi.testclient import TestClient
    from psycopg import sql
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.engine import make_url

    from alembic import command
    from app.core.config import BACKEND_ROOT, Settings
    from app.main import create_app

    source = make_url(os.environ["TEST_DATABASE_URL"])
    assert source.host in {"localhost", "127.0.0.1"} and source.database.endswith("_test")
    name = "ocr_jobs_" + uuid4().hex + "_test"
    admin = source.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = source.set(database=name).render_as_string(hide_password=False)
    engine = create_engine(url, hide_parameters=True)
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    try:
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "0011_gt_prefill")
            assert "ocr_jobs" not in inspect(conn).get_table_names()
            command.upgrade(cfg, "head")
            assert "ocr_jobs" in inspect(conn).get_table_names()
            command.check(cfg)
        app = create_app(
            Settings(
                _env_file=None,
                database_url=url,
                storage_path=tmp_path / "uploads",
                model_gateway_base_url="https://synthetic.invalid",
                model_gateway_api_key="test-only-credential",
            )
        )
        with TestClient(app) as client:
            doc = client.post(
                "/api/documents", files={"file": ("synthetic.png", png, "image/png")}
            ).json()
            case, _ = layout(client, doc)
            pid = pipeline(client)
            worker, create = paused_worker(client)
            jid = create(case, [pid])
            rivals = [
                JobWorker(worker.database, worker.settings, worker.storage, asyncio.Lock())
                for _ in range(2)
            ]
            barrier = Barrier(2)

            def claim(w):
                barrier.wait()
                return w.claim()[0]

            with ThreadPoolExecutor(max_workers=2) as pool:
                claimed = list(pool.map(claim, rivals))
            assert claimed.count(jid) == 1 and claimed.count(None) == 1
            winner = rivals[claimed.index(jid)]
            with worker.database.session_factory() as s:
                job = s.get(OCRJob, jid)
                job.lease_expires_at = now() - timedelta(seconds=1)
                s.commit()
            assert worker.claim()[0] == jid
            asyncio.run(worker.execute(jid))
            final = client.get(f"/api/ocr-jobs/{jid}").json()
            assert final["status"] == "completed" and final["attempt_count"] == 2
            with pytest.raises(LostLease):
                winner.heartbeat(jid)
    finally:
        engine.dispose()
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
