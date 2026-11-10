import asyncio

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.db.models import PipelineRun
from app.pipelines.hutch_crop import HutchCropPipelineAdapter
from app.pipelines.hutch_full import HutchFullPipelineAdapter
from app.pipelines.mint import MintPipelineAdapter
from app.services.image_service import ImageService
from tests.test_gateway_and_fairness import config, multipart

pytestmark = pytest.mark.usefixtures("registered_catalog")


@pytest.mark.parametrize("roi", [None, {"x1": 40, "y1": 30, "x2": 270, "y2": 150}, {"x1": 0, "y1": 0, "x2": 300, "y2": 200}])
def test_full_preserves_canonical_input_without_recropping(settings, png, gateway, monkeypatch, roi):
    with ImageService.open(png) as original:
        crop = ImageService(settings).canonical_crop(original, roi)
        def forbidden(*args, **kwargs):
            pytest.fail("Adapter must reuse canonical crop bytes")
        monkeypatch.setattr(ImageService, "canonical_crop", forbidden)
        adapter = HutchFullPipelineAdapter(config("hutch_full"), settings)
        adapter.config.query_params = {"roi": "obsolete", "engine": "custom"}
        assert adapter.prepare_input(original, crop, roi) is crop
        result = asyncio.run(adapter.run(original_image=original, cropped_image=crop, roi=roi))
        request = gateway[1][-1]
        fields = multipart(request)
        assert fields["image"] == crop.png
        assert set(fields) == {"image", "text_det_unclip_ratio", "text_det_thresh", "text_det_box_thresh"}
        assert adapter.model_parameters() == {"text_det_unclip_ratio": 1.7, "text_det_thresh": 0.25, "text_det_box_thresh": 0.6}
        assert dict(request.url.params) == {"engine": "paddle"}
        assert result.diagnostics["roi"] == roi
        assert result.diagnostics["crop_sha256"] == crop.sha256
        assert result.diagnostics["input_sha256"] == crop.sha256
        assert result.diagnostics["crop_stage"] == "app_crop"


def test_missing_key_has_no_fake_fallback(client, case, settings, gateway):
    settings.model_gateway_api_key = SecretStr("")
    result = client.post(f"/api/test-cases/{case['id']}/run", json={"pipelines": ["mint", "hutch_crop", "hutch_full"]}).json()
    assert {r["error_code"] for r in result["runs"]} == {"MISSING_GATEWAY_KEY"}
    assert all(r["final_text"] is None and r["metrics"] is None for r in result["runs"])
    assert not gateway[1]


def test_archived_history_excluded_without_deleting_data(client, case):
    client.post(f"/api/test-cases/{case['id']}/run", json={"pipelines": ["mint", "hutch_crop"]})
    with client.app.state.database.session_factory() as session:
        runs = session.scalars(select(PipelineRun)).all()
        for run in runs:
            run.archived = True
        session.commit()
    assert client.get(f"/api/test-cases/{case['id']}").json()["runs"] == []
    assert client.get(f"/api/test-cases/{case['id']}/results").json()["runs"] == []
    assert all(r["tests"] == 0 for r in client.get("/api/matrix").json())
    assert all(r["tests"] == 0 for c in client.get("/api/analytics/categories").json() for r in c["pipelines"])
    # Archiving hides runs, not the tagged source cases counted in the inventory.
    categories = client.get("/api/analytics/categories").json()
    assert next(c for c in categories if c["code"] == "thai_text")["test_cases"] == 1
    with client.app.state.database.session_factory() as session:
        runs = session.scalars(select(PipelineRun)).all()
        assert len(runs) == 2 and all((r.raw_text or r.final_text) and r.metric_records for r in runs)


def test_mode_is_not_a_product_setting(client):
    assert client.put("/api/pipelines/mint", json={"mode": "mock"}).status_code == 422
    assert all("mode" not in config for config in client.get("/api/pipelines").json())


@pytest.mark.parametrize("shared_key", ["", "shared-test-only-credential"])
def test_one_shared_key_and_boolean_only_status(client, settings, monkeypatch, shared_key):
    settings.model_gateway_api_key = SecretStr(shared_key)
    for variable in ("MINT_API_KEY", "HUTCH_API_KEY", "HUTCH_FULL_API_KEY"):
        monkeypatch.setenv(variable, "obsolete-test-only-credential")
    for pipeline_id, adapter_type in (
        ("mint", MintPipelineAdapter), ("hutch_crop", HutchCropPipelineAdapter),
        ("hutch_full", HutchFullPipelineAdapter),
    ):
        assert settings.api_key(pipeline_id) == shared_key
        adapter = adapter_type(config(pipeline_id), settings)
        assert adapter.gateway.key == shared_key
        headers = adapter.gateway.headers("test-request-id")
        assert headers.get("Authorization") == (f"Bearer {shared_key}" if shared_key else None)
        data = client.get(f"/api/pipelines/{pipeline_id}").json()
        assert data["api_key_configured"] is bool(shared_key)
        assert [key for key in data if "key" in key.lower()] == ["api_key_configured"]
    response = client.get("/api/pipelines")
    if shared_key:
        assert shared_key not in response.text
    assert "obsolete-test-only-credential" not in response.text


def test_shared_gateway_ignores_stale_pipeline_hosts(client, settings, gateway):
    from app.db.models import PipelineConfig
    from app.services.auto_roi_service import AutoROIService

    with client.app.state.database.session_factory() as session:
        records = session.scalars(select(PipelineConfig)).all()
        for record in records:
            record.base_url = "https://stale.example"
        session.commit()
        for record, adapter_type in zip(records, (
            MintPipelineAdapter, HutchCropPipelineAdapter, HutchFullPipelineAdapter,
        )):
            adapter = adapter_type(record, settings)
            assert adapter.gateway.base_url == settings.model_gateway_base_url
            assert adapter.gateway.key == settings.model_gateway_api_key.get_secret_value()
        auto_roi = AutoROIService(session, settings, None)
        assert auto_roi.gateway.base_url == settings.model_gateway_base_url
        assert auto_roi.gateway.key == settings.model_gateway_api_key.get_secret_value()
    assert all(row["base_url"] == settings.model_gateway_base_url
               for row in client.get("/api/pipelines").json())
    client.post("/api/pipelines/mint/test-connection")
    assert gateway[1]
    assert all(str(request.url).startswith(settings.model_gateway_base_url + "/")
               for request in gateway[1])
