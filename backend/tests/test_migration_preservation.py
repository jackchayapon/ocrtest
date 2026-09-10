from datetime import datetime, timezone
from uuid import uuid4

from alembic.config import Config
from sqlalchemy import MetaData, Table, create_engine, inspect, select

from alembic import command
from app.core.config import BACKEND_ROOT


def test_upgrade_downgrade_preserves_real_and_historical_results(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0003_pdf_pages")
        metadata = MetaData()
        metadata.reflect(connection)
        tables = metadata.tables
        now = datetime.now(timezone.utc)
        document, case = uuid4().hex, uuid4().hex
        connection.execute(tables["documents"].insert().values(
            id=document, filename="preserved.png", mime_type="image/png", width=300, height=200,
            storage_key="preserved.png", created_at=now,
        ))
        connection.execute(tables["test_cases"].insert().values(
            id=case, document_id=document, ground_truth_raw="preserved ground truth",
            status="confirmed", created_at=now, updated_at=now,
        ))
        ids = []
        for flagged, payload in [(False, {"data": {"text": "real"}}), (True, {}), (False, {"mode": "mock"})]:
            run = uuid4().hex
            ids.append(run)
            connection.execute(tables["pipeline_runs"].insert().values(
                id=run, test_case_id=case, pipeline_id="mint", pipeline_name="Mint", status="success",
                raw_text="preserve prediction", final_text="preserve prediction", boxes=[],
                raw_response=payload, is_mock=flagged, crop_sha256="a" * 64,
                crop_width=100, crop_height=60, crop_stage="pre_adapter", created_at=now,
            ))
            connection.execute(tables["metrics"].insert().values(
                id=uuid4().hex, pipeline_run_id=run, text_kind="final", cer=0.3,
                wer=0.5, exact_match=False, created_at=now,
            ))
        command.upgrade(cfg, "head")
        runs = Table("pipeline_runs", MetaData(), autoload_with=connection)
        records = {r.id: r for r in connection.execute(select(runs))}
        assert [records[i].archived for i in ids] == [False, True, True]
        assert all(records[i].input_sha256 == "a" * 64 for i in ids)
        assert all(records[i].input_width == 100 and records[i].crop_stage == "pre_adapter" for i in ids)
        assert len(connection.execute(select(tables["metrics"])).all()) == 3
        assert connection.execute(select(tables["test_cases"].c.ground_truth_raw)).scalar_one() == "preserved ground truth"
        assert "mode" not in {c["name"] for c in inspect(connection).get_columns("pipeline_configs")}
        command.downgrade(cfg, "0003_pdf_pages")
        old = Table("pipeline_runs", MetaData(), autoload_with=connection)
        records = {r.id: r for r in connection.execute(select(old))}
        assert [records[i].is_mock for i in ids] == [False, True, True]
        assert all(records[i].raw_text == "preserve prediction" for i in ids)
        assert len(connection.execute(select(tables["metrics"])).all()) == 3
        command.upgrade(cfg, "head")
    engine.dispose()
