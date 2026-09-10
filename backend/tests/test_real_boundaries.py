import asyncio
import io
from hashlib import sha256

import pytest
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import select

from app.db.models import PipelineRun
from app.integrations.model_gateway import GatewayError
from app.pipelines.hutch_full import HutchFullPipelineAdapter
from app.services.image_service import ImageService
from tests.test_gateway_and_fairness import config


@pytest.mark.parametrize("roi", [None, {"x1": 40, "y1": 30, "x2": 270, "y2": 150}])
def test_full_preserves_source_without_crop(settings, png, gateway, monkeypatch, roi):
    original = ImageService.open(png)
    def forbidden(*args, **kwargs):
        pytest.fail("Hutch Full must never crop locally")
    monkeypatch.setattr(ImageService, "crop", forbidden)
    monkeypatch.setattr(ImageService, "canonical_crop", forbidden)
    adapter = HutchFullPipelineAdapter(config("hutch_full"), settings)
    source = adapter.prepare_input(original, None, roi)
    assert source.png == ImageService.encode_png(original)
    assert Image.open(io.BytesIO(source.png)).tobytes() == original.tobytes()
    assert (source.width, source.height) == original.size
    assert source.roi == roi
    assert source.sha256 == sha256(source.png).hexdigest()
    assert adapter.model_parameters() == {"text_det_unclip_ratio": 1.7, "text_det_thresh": 0.25, "text_det_box_thresh": 0.6}
    with pytest.raises(GatewayError) as error:
        asyncio.run(adapter.run(original_image=original, roi=roi))
    assert error.value.code == "ROI_CONTRACT_UNCONFIRMED"
    assert not gateway[1], "Unproven ROI serialization must not reach the network"
    assert adapter.diagnostics["crop_sha256"] is None
    assert adapter.diagnostics["input_sha256"] == source.sha256
    assert adapter.diagnostics["crop_stage"] == "external_hutch"


def test_missing_key_has_no_fake_fallback(client, case, settings, gateway):
    settings.model_gateway_api_key = SecretStr("")
    settings.mint_api_key = settings.hutch_api_key = settings.hutch_full_api_key = SecretStr("")
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
    assert all(c["test_cases"] == 0 for c in client.get("/api/analytics/categories").json())
    with client.app.state.database.session_factory() as session:
        runs = session.scalars(select(PipelineRun)).all()
        assert len(runs) == 2 and all(r.raw_text and r.metric_records for r in runs)


def test_mode_is_not_a_product_setting(client):
    assert client.put("/api/pipelines/mint", json={"mode": "mock"}).status_code == 422
    assert all("mode" not in config for config in client.get("/api/pipelines").json())
