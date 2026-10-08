"""Reproducible synthetic-only DB read audit. Never reads the application's .env.

Default: temporary SQLite. --postgres: create a NEW local *_test database using
TEST_DATABASE_URL (localhost only). Generated DBs are retained for inspection.
--backend-root can point at a git archive of the baseline backend plus the same
numeric diagnostics module, without modifying the working tree.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

ROOT = Path(__file__).resolve().parents[1]


def seed_fixture(app, lean, case_count=30, repeats=1, mixed=False):
    from app.db.models import (
        Document,
        GlobalField,
        Metric,
        OCRField,
        PipelineConfig,
        PipelineRun,
    )
    from app.db.models import TestCase as Case
    from app.services.field_service import compact_comparison

    def stable_id(name):
        return str(uuid5(NAMESPACE_URL, "ocrtest/traffic/" + name))

    epoch = datetime(2026, 10, 1, tzinfo=timezone.utc)
    with app.state.database.session_factory() as session:
        configs = [
            PipelineConfig(
                id=stable_id(f"config/{i}"),
                created_at=epoch + timedelta(seconds=i),
                updated_at=epoch,
                pipeline_id=f"audit_{i}",
                name=f"Synthetic {i}",
                execution_mode="integrated",
                source="custom",
                integrated_options={
                    "version": "6",
                    "det_weight": "baseline",
                    "rec_weight": "baseline",
                },
            )
            for i in range(5)
        ]
        session.add_all(configs)
        for i in range(case_count):
            document = Document(
                id=stable_id(f"document/{i}"),
                created_at=epoch + timedelta(seconds=i),
                filename=f"synthetic_{i}.png",
                mime_type="image/png",
                width=600,
                height=400,
                storage_key=f"synthetic_{i}.png",
            )
            case = Case(
                id=stable_id(f"case/{i}"),
                created_at=epoch + timedelta(seconds=i),
                updated_at=epoch,
                document=document,
                roi={"x1": 0, "y1": 0, "x2": 600, "y2": 400},
                ground_truth_raw="Synthetic GT",
                ground_truth_normalized="Synthetic GT",
                status="confirmed",
            )
            if mixed and i % 3:
                case.workflow = "global"
                case.evaluation_mode = "per_field" if i % 3 == 1 else "whole_document"
                case.document_gt_confirmed_at = epoch if i % 3 == 2 else None
                case.global_fields = [GlobalField(
                    id=stable_id(f"global/{i}/{j}"), field_index=j + 1,
                    roi={"x1": 0, "y1": j * 40, "x2": 100, "y2": (j + 1) * 40},
                    source="manual", ground_truth_raw="Synthetic GT",
                    ground_truth_normalized="Synthetic GT", confirmed_at=epoch,
                ) for j in range(3)]
            session.add(case)
            for index, config in enumerate(configs * repeats):
                run = PipelineRun(
                    id=stable_id(f"run/{i}/{index}"),
                    created_at=epoch + timedelta(seconds=i, microseconds=index),
                    pipeline_id=config.pipeline_id,
                    pipeline_name=config.name,
                    status="success",
                    final_text="Synthetic OCR",
                    raw_text=None,
                    normalized_text="Synthetic OCR",
                    confidence=0.9,
                    processing_time_ms=1200,
                    gateway_duration_ms=1000,
                    crop_stage="global_fields" if case.workflow == "global" else "app_crop",
                    document_evaluation={"cer": 0.1, "evaluated_at": epoch.isoformat()}
                    if case.workflow == "global" else None,
                    boxes=[
                        {
                            "polygon": [[0, 0], [100, 0], [100, 40], [0, 40]],
                            "text": "Synthetic OCR",
                        }
                    ]
                    * 20,
                    raw_response={"engine": "synthetic"}
                    if lean
                    else {"synthetic_legacy_diagnostics": "x" * 4096},
                )
                run.metric_records = [
                    Metric(
                        id=stable_id(f"metric/{i}/{index}"),
                        created_at=epoch + timedelta(seconds=i, microseconds=index),
                        text_kind="final",
                        cer=0.1,
                        wer=0.2,
                        exact_match=False,
                    )
                ]
                run.fields = [
                    OCRField(
                        id=stable_id(f"field/{i}/{index}/{j}"),
                        created_at=epoch,
                        updated_at=epoch,
                        field_index=j,
                        global_field_id=case.global_fields[j].id if case.workflow == "global" else None,
                        geometry={"bbox": [0, 0, 100, 40]},
                        ocr_text="Synthetic OCR",
                        ground_truth_raw="Synthetic GT",
                        confirmed_at=epoch,
                        evaluation=compact_comparison("Synthetic OCR", "Synthetic GT"),
                        diagnostics={"status": "success"}
                        if lean
                        else {"synthetic_legacy": "y" * 2048},
                    )
                    for j in range(3)
                ]
                case.runs.append(run)
        session.commit()


def normalized_hash(value):
    # Independently created fixtures have different generated IDs and timestamps.
    # Strict response equality on ONE fixture is additionally covered by pytest.
    if isinstance(value, dict):
        value = {k: v for k, v in value.items() if k != "computation_ms"}
    text = json.dumps(value, sort_keys=True, ensure_ascii=False)
    text = re.sub(
        r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", "GENERATED_ID", text
    )
    text = re.sub(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:\+\d\d:\d\d|Z)?", "TIMESTAMP", text
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def measure(database_url, temp, lean, case_count=30, repeats=1, mixed=False):
    from app.core.config import Settings
    from app.db.diagnostics import ReadStats, current_stats, install_diagnostics
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app(
        Settings(
            _env_file=None,
            database_url=database_url,
            storage_path=Path(temp) / "uploads",
            model_gateway_base_url="https://synthetic.invalid",
            model_gateway_api_key="",
        )
    )
    install_diagnostics(app.state.database.engine)
    endpoints = [
        "/api/pipelines",
        "/api/pipelines/models",
        "/api/categories",
        "/api/document-types",
        "/api/history?limit=20",
        "/api/history?limit=20&view=summary",
        "/api/history?limit=20&view=summary&latest=true",
        "/api/matrix",
        "/api/analytics/summary",
        "/api/analytics/pipelines",
        "/api/analytics/categories",
        "/api/analytics/comparison",
        "/api/analytics/errors",
    ]
    endpoints.append('/api/analytics/errors?test_case_id=' + str(uuid5(NAMESPACE_URL, 'ocrtest/traffic/case/0')))
    results = {}
    with TestClient(app) as client:
        seed_fixture(app, lean, case_count, repeats, mixed)
        for endpoint in endpoints:
            samples = []
            for _ in range(3):
                stats = ReadStats()
                token = current_stats.set(stats)
                try:
                    response = client.get(endpoint)
                    assert response.status_code == 200, (endpoint, response.status_code)
                    samples.append(
                        dict(
                            **asdict(stats),
                            response_bytes=len(response.content),
                            normalized_output_sha256=normalized_hash(response.json()),
                        )
                    )
                finally:
                    current_stats.reset(token)
            results[endpoint] = samples

        from app.services.matrix_service import MatrixService
        bundled = hasattr(MatrixService, "dashboard")
        workload = ["/api/analytics/summary?dashboard=true"] if bundled else [
            "/api/analytics/summary", "/api/matrix", "/api/analytics/comparison"]
        samples = []
        for _ in range(3):
            stats = ReadStats()
            token = current_stats.set(stats)
            try:
                responses = [client.get(path) for path in workload]
                assert all(r.status_code == 200 for r in responses)
                data = responses[0].json() if bundled else {
                    **responses[0].json(), "matrix": responses[1].json(), "comparison": responses[2].json()}
                # Timing is not part of the statistical output contract.
                data["comparison"].pop("computation_ms", None)
                samples.append(dict(**asdict(stats), requests=len(responses),
                    response_bytes=sum(len(r.content) for r in responses),
                    normalized_output_sha256=normalized_hash(data)))
            finally:
                current_stats.reset(token)
        results["dashboard_workload"] = samples
        if hasattr(app.state, "config_cache"):
            app.state.config_cache.invalidate("models")
        def concurrent_read(_):
            stats = ReadStats()
            token = current_stats.set(stats)
            try:
                response = client.get("/api/pipelines/models")
                assert response.status_code == 200
                return dict(**asdict(stats), response_bytes=len(response.content),
                    normalized_output_sha256=normalized_hash(response.json()))
            finally:
                current_stats.reset(token)
        with ThreadPoolExecutor(max_workers=8) as pool:
            concurrent = list(pool.map(concurrent_read, range(8)))
    return {
        "fixture": {
            "cases": case_count,
            "runs": case_count * 5 * repeats,
            "ocr_fields": case_count * 15 * repeats,
            "runs_per_pipeline": repeats,
            "pipelines": 5,
            "legacy_json": not lean,
            "mixed_workflows": mixed,
        },
        "database": app.state.database.engine.dialect.name,
        "units": "estimated fetched-value UTF-8 bytes; NOT wire bytes or Neon billed bytes",
        "endpoints": results,
        "concurrent_models": concurrent,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--postgres", action="store_true")
    parser.add_argument("--lean", action="store_true")
    parser.add_argument("--backend-root", type=Path, default=ROOT / "backend")
    parser.add_argument("--mixed", action="store_true", help="Include Global per-field and whole-document workflows")
    parser.add_argument("--cases", type=int, default=30)
    parser.add_argument("--runs-per-pipeline", type=int, default=1)
    args = parser.parse_args()
    if not (1 <= args.cases <= 500 and 1 <= args.runs_per_pipeline <= 10):
        parser.error("Synthetic fixture bounds: cases 1..500, runs-per-pipeline 1..10")
    sys.path.insert(0, str(args.backend_root.resolve()))
    (ROOT / ".runtime").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / ".runtime") as temp:
        url = f"sqlite:///{Path(temp).as_posix()}/audit.db"
        if args.postgres:
            import psycopg
            from psycopg import sql
            from sqlalchemy.engine import make_url

            source = make_url(os.environ.get("TEST_DATABASE_URL", ""))
            if source.host not in {"127.0.0.1", "localhost"} or not (
                source.database or ""
            ).endswith("_test"):
                raise RuntimeError(
                    "Only an explicit local PostgreSQL *_test source is accepted"
                )
            name = "neon_probe_" + uuid4().hex + "_test"
            admin = source.set(drivername="postgresql", database="postgres")
            with psycopg.connect(
                admin.render_as_string(hide_password=False), autocommit=True
            ) as connection:
                connection.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name))
                )
            url = source.set(
                drivername="postgresql+psycopg", database=name
            ).render_as_string(hide_password=False)
        report = measure(url, temp, args.lean, args.cases, args.runs_per_pipeline, args.mixed)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        "Synthetic traffic report saved; no user data, credentials or real Gateway calls."
    )


if __name__ == "__main__":
    main()
