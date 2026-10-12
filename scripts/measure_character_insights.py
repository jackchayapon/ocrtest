"""Synthetic local PostgreSQL benchmark. Never load .env or contact Model Gateway.
Run with backend Python; TEST_DATABASE_URL must identify localhost *_test.
Creates and retains a fresh database. Output contains numerical measurements only.
"""

import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from statistics import median
from time import perf_counter
from uuid import NAMESPACE_URL, uuid4, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    import psycopg
    from app.core.config import Settings
    from app.db.diagnostics import ReadStats, current_stats, install_diagnostics
    from app.db.models import TestCase
    from app.main import create_app
    from app.services.field_service import compact_comparison
    from fastapi.testclient import TestClient
    from measure_db_traffic import seed_fixture
    from psycopg import sql
    from sqlalchemy import select
    from sqlalchemy.engine import make_url

    source = make_url(os.environ["TEST_DATABASE_URL"])
    if source.host not in {"localhost", "127.0.0.1"} or not source.database.endswith(
        "_test"
    ):
        raise RuntimeError("Only local *_test PostgreSQL is accepted")
    name = "character_probe_" + uuid4().hex + "_test"
    with psycopg.connect(
        source.set(drivername="postgresql", database="postgres").render_as_string(
            hide_password=False
        ),
        autocommit=True,
    ) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = source.set(drivername="postgresql+psycopg", database=name).render_as_string(
        hide_password=False
    )
    with tempfile.TemporaryDirectory(dir=ROOT / ".runtime") as temp:
        app = create_app(
            Settings(
                _env_file=None,
                database_url=url,
                storage_path=Path(temp),
                model_gateway_base_url="https://no-network.invalid",
            )
        )
        install_diagnostics(app.state.database.engine)
        with TestClient(app) as client:
            seed_fixture(app, lean=False, case_count=20, repeats=3, mixed=True)
            # Make all global snapshots valid; retain historical runs and vendor blobs.
            with app.state.database.session_factory() as session:
                for case in session.scalars(select(TestCase)):
                    if case.workflow == "global":
                        for run in case.runs:
                            for field in run.fields:
                                field.ground_truth_raw = "Synthetic GT"
                                field.evaluation = compact_comparison(
                                    field.ocr_text, "Synthetic GT"
                                )
                            prediction = "\n".join(f.ocr_text for f in run.fields)
                            run.document_evaluation = compact_comparison(
                                prediction, case.ground_truth_raw
                            )
                session.commit()
            case_id = str(uuid5(NAMESPACE_URL, "ocrtest/traffic/case/19"))
            field_id = str(uuid5(NAMESPACE_URL, "ocrtest/traffic/global/19/0"))

            def measure(path, payload=None):
                readings = []
                for _ in range(3):
                    stats = ReadStats()
                    token = current_stats.set(stats)
                    started = perf_counter()
                    try:
                        response = (
                            client.post(path, json=payload)
                            if payload is not None
                            else client.get(path)
                        )
                        assert response.status_code == 200, response.status_code
                    finally:
                        current_stats.reset(token)
                    readings.append(
                        dict(
                            **asdict(stats),
                            http_bytes=len(response.content),
                            latency_ms=round((perf_counter() - started) * 1000, 2),
                            requests=1,
                        )
                    )
                return {key: median(r[key] for r in readings) for key in readings[0]}

            detail = f"/api/test-cases/{case_id}"
            case_payload = client.get(f"/api/test-cases/{case_id}").json()
            export_selection = {
                "mode": "per_field",
                "pipeline_ids": [f"audit_{i}" for i in range(5)],
                "run_ids": [
                    str(uuid5(NAMESPACE_URL, f"ocrtest/traffic/run/19/{i + 10}"))
                    for i in range(5)
                ],
                "field_ids": [
                    str(uuid5(NAMESPACE_URL, f"ocrtest/traffic/global/19/{i}"))
                    for i in range(3)
                ],
                "revision": case_payload["updated_at"],
            }
            rows = {
                "A_history_before": measure(
                    "/api/history?view=summary&latest=true&limit=20"
                ),
                "A_history_after": measure(
                    "/api/history?view=summary&latest=true&compact=true&limit=20"
                ),
                "B_overlay_source_baseline": measure(detail),
                "B_overlay_after": measure(
                    detail + "/error-summary?pipeline_id=audit_0"
                ),
                "C_evaluation_before_and_after": measure(detail),
                "D_expand_before_loaded_alignment": {
                    "queries": 0,
                    "estimated_result_bytes": 0,
                    "http_bytes": 0,
                    "requests": 0,
                    "latency_ms": 0,
                },
                "D_expand_after": measure(
                    detail + f"/error-summary?pipeline_id=audit_0&field_id={field_id}"
                ),
                "E_export_source_baseline": measure(detail),
                "E_export_after": measure(detail + "/evaluation-report"),
                "F_excel_selected": measure(
                    detail + "/evaluation-excel", export_selection
                ),
            }
    report = {
        "fixture": "20 cases, 5 pipelines, 3 runs per pipeline, 3 fields; mixed legacy/global",
        "method": "Median of 3 sequential warm-process requests; estimated UTF-8 DBAPI values, NOT Neon billed transfer",
        "baseline": "Unchanged main case/summary endpoints on same fixture. Overlay/export did not exist on main; source baseline is equivalent full-case read, NOT a prior implemented export.",
        "notes": "D adds one explicit request for server-authoritative statistics; closed summaries issue none. C remains existing full evaluation payload. No OCR or external requests.",
        "measurements": rows,
    }
    output = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / ".runtime/character-insights-traffic.json"
    )
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Saved synthetic performance measurements:", output)


if __name__ == "__main__":
    main()
