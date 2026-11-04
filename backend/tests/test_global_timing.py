import asyncio

import pytest
from sqlalchemy import select

from app.db.models import PipelineRun
from app.integrations.model_gateway import GatewayError
from app.pipelines.base import PipelineResult
from tests.test_global_layout import layout


@pytest.mark.parametrize("tasks", [1, 2])
@pytest.mark.parametrize("pipelines", [1, 2])
@pytest.mark.parametrize("failed", [False, True])
def test_global_wall_clock_persists_without_summing_parallel_fields(
    client, document, monkeypatch, tasks, pipelines, failed,
):
    client.app.state.settings.ocr_max_concurrent_tasks = tasks
    client.app.state.settings.ocr_max_concurrent_fields = 2
    case, fields = layout(client, document)
    root = f"/api/test-cases/{case['id']}"
    client.put(root + "/ground-truth", json={"ground_truth_raw": "synthetic"})
    models = client.get("/api/pipelines/models").json()
    rec = next(m for m in models if m["kind"] == "rec" and m["source"] == "custom")
    ids = [client.post("/api/pipelines", json={
        "name": f"Timing {i}", "source": "custom", "execution_mode": "rec",
        "rec_model_id": rec["id"],
    }).json()["pipeline_id"] for i in range(pipelines)]

    async def infer(self, **kwargs):
        await asyncio.sleep(.02)
        if failed and self.config.pipeline_id == ids[0] and kwargs["roi"] == fields[0]["roi"]:
            raise GatewayError("synthetic failure", "UPSTREAM_MODEL_ERROR")
        return PipelineResult(self.config.pipeline_id, self.config.name, "ok", "ok", .9, 20,
                              diagnostics={"gateway_duration_ms": 10})

    monkeypatch.setattr("app.pipelines.dynamic.DynamicRecognitionAdapter.run", infer)
    response = client.post(root + "/run", json={"pipelines": ids})
    assert response.status_code == 200, response.text
    saved = client.get(root).json()["runs"]
    for run in saved:
        assert run["timing_semantics"] == "wall_clock_v1"
        assert run["processing_time_ms"] == run["wall_time_ms"]
        assert run["run_wall_time_ms"] >= run["wall_time_ms"] >= 15
        assert run["total_field_compute_ms"] >= 35
        assert [f["global_field_id"] for f in run["fields"]] == [f["id"] for f in fields]
        assert run["gateway_duration_ms"] == (10 if failed and run["pipeline_id"] == ids[0] else 20)
    assert saved[0]["status"] == ("error" if failed else "success")
    if tasks == 2 and pipelines == 1:
        assert saved[0]["wall_time_ms"] < saved[0]["total_field_compute_ms"]
    # Summary must not load raw_response merely to fetch timing; the detail contract
    # explicitly distinguishes legacy records from new wall-clock values.
    assert client.get("/api/history?view=summary&latest=true").status_code == 200
    with client.app.state.database.session_factory() as session:
        record = session.scalar(select(PipelineRun).where(PipelineRun.id == saved[0]["id"]))
        record.raw_response = None
        record.processing_time_ms = 9999
        session.commit()
    legacy = client.get(root).json()["runs"][0]
    assert legacy["processing_time_ms"] == 9999
    assert legacy["timing_semantics"] == "legacy_recorded"
    assert legacy["wall_time_ms"] is None and legacy["total_field_compute_ms"] is None
