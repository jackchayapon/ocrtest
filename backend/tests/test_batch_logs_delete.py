import asyncio
import io
import json

import httpx
import pytest
from PIL import Image
from sqlalchemy import func, select

from app.db.models import AppLog, Category, Document, Metric, PipelineRun, test_case_categories
from app.db.models import TestCase as Case
from app.integrations.model_gateway import GatewayError, ModelGatewayClient
from app.services.log_service import LogService
from app.services.pipeline_manager import PipelineManager
from app.services.test_case_service import TestCaseService as CaseService
from tests.test_gateway_and_fairness import envelope, multipart
from tests.test_pdf import pdf_fixture


class LargeJSON(httpx.AsyncByteStream):
    def __init__(self, mb):
        self.mb = mb

    async def __aiter__(self):
        yield b'{"data":{"image":"'
        for _ in range(self.mb):
            yield b"x" * (1024 * 1024)
        yield b'","text":"okay"},"meta":{"request_id":"large-fixture","duration_ms":1}}'


@pytest.mark.parametrize("mb,limit,success", [(17, 64, True), (63, 64, True), (65, 64, False), (2, 1, False)])
def test_bounded_gateway_response(settings, monkeypatch, mb, limit, success):
    assert settings.model_gateway_max_response_mb == 64
    settings.model_gateway_max_response_mb = limit
    gateway = ModelGatewayClient(settings)
    monkeypatch.setattr(gateway, "_client", lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=LargeJSON(mb)))
    ))
    async def send():
        return await gateway.send(gateway.build_request(png=b"test", endpoint="/api/v1/ocr-results",
                                  query_params={"engine": "custom"}, fields={}, request_id="bounded"))
    if success:
        result = asyncio.run(send())
        assert result["data"]["text"] == "okay"
        assert len(json.dumps(result)) < 1000
        assert result["meta"]["request_id"] == "large-fixture"
    else:
        with pytest.raises(GatewayError) as error:
            asyncio.run(send())
        assert error.value.code == "RESPONSE_TOO_LARGE"
        assert "ผลลัพธ์ที่ Gateway ส่งกลับ" in str(error.value)
        assert f"{limit} MB" in str(error.value)


def test_batch_order_failure_independence_and_safe_logs(client, gateway, monkeypatch):
    doc = client.post("/api/documents", files={"file": ("pages.pdf", pdf_fixture(3), "application/pdf")}).json()
    state = {"active": 0, "max": 0, "order": []}
    original_run = PipelineManager.run

    async def observed(self, configs, original, crop, roi, roi_source="none"):
        state["active"] += 1
        state["max"] = max(state["max"], state["active"])
        state["order"].append(("start", original.width))
        await asyncio.sleep(0.01)
        try:
            return await original_run(self, configs, original, crop, roi, roi_source)
        finally:
            state["order"].append(("end", original.width))
            state["active"] -= 1
    monkeypatch.setattr(PipelineManager, "run", observed)

    def upstream(request):
        fields = multipart(request)
        assert set(fields) <= {"image", "text_det_unclip_ratio", "text_det_thresh", "text_det_box_thresh"}
        width = Image.open(io.BytesIO(fields["image"])).width
        if width == 1200:
            return httpx.Response(503, json={"error": {"code": "MODEL_UNAVAILABLE", "message": "test-gateway-secret"}})
        return httpx.Response(200, json=envelope(request.url.params["engine"]))
    gateway[0]["handler"] = upstream
    result = client.post(f"/api/documents/{doc['id']}/run-pages", json={
        "pages": [3, 1, 2, 1], "pipelines": ["mint", "hutch_crop", "hutch_full"],
        "category_codes": ["thai_text", "blur"],
    })
    assert result.status_code == 200
    events = [json.loads(line) for line in result.text.splitlines()]
    assert [e["page"] for e in events if e["event"] == "page_started"] == [1, 2, 3]
    completed = [e for e in events if e["event"] in ("page_success", "page_error")]
    assert [e["status"] for e in completed] == ["success", "error", "success"]
    assert state["max"] == 1
    assert state["order"] == [(kind, width) for width in (1000, 1200, 1400) for kind in ("start", "end")]
    records = [client.get(f"/api/test-cases/{e['test_case_id']}").json() for e in completed]
    assert len({r["id"] for r in records}) == 3
    assert all(len(r["runs"]) == 3 and r["ground_truth_raw"] is None for r in records)
    assert all({c["code"] for c in r["categories"]} == {"thai_text", "blur"} for r in records)
    for record in records:
        assert record["roi"]["x2"] == record["document"]["width"]
        assert record["runs"][2]["roi"] is None
        assert record["runs"][2]["crop_stage"] == "full_image"
    client.put(f"/api/test-cases/{records[0]['id']}/ground-truth", json={"ground_truth_raw": "private truth"})
    assert client.get(f"/api/test-cases/{records[2]['id']}").json()["ground_truth_raw"] is None
    logs = client.get("/api/logs?limit=100").json()
    assert "private truth" not in json.dumps(logs) and "test-gateway-secret" not in json.dumps(logs)
    assert client.get("/api/logs?level=ERROR").json()["total"] == 4
    assert client.get("/api/logs?event_type=batch_finished").json()["total"] == 1
    assert client.get("/api/logs?pipeline=mint").json()["total"] == 3
    assert len(client.get("/api/logs?limit=2&offset=2").json()["items"]) == 2
    assert client.get("/api/logs?date_from=2099-01-01T00:00:00Z").json()["total"] == 0
    run_id = records[0]["runs"][0]["request_id"]
    assert client.get("/api/logs", params={"request_id": run_id}).json()["total"] == 1
    analysis = client.get("/api/analytics/categories?category=blur").json()[0]
    assert analysis["test_cases"] == 3
    assert all(p["successful_runs"] == 2 and p["failed_runs"] == 1
               for p in analysis["pipelines"] if p["pipeline_id"] != "benchmark")
    assert next(p for p in analysis["pipelines"] if p["pipeline_id"] == "benchmark")["tests"] == 0


@pytest.mark.parametrize("pages", [[0], [4], [True], [1.5], [], ["1"]])
def test_batch_rejects_bad_pages(client, pages):
    doc = client.post("/api/documents", files={"file": ("p.pdf", pdf_fixture(), "application/pdf")}).json()
    assert client.post(f"/api/documents/{doc['id']}/run-pages", json={"pages": pages, "pipelines": ["mint"]}).status_code == 422


def test_delete_cascades_preserves_shared_document_and_audit(client, case):
    other = client.post("/api/test-cases", json={"document_id": case["document"]["id"]}).json()
    client.put(f"/api/test-cases/{case['id']}/categories", json={"category_codes": ["blur"]})
    client.put(f"/api/test-cases/{case['id']}/ground-truth", json={"ground_truth_raw": "secret truth"})
    client.post(f"/api/test-cases/{case['id']}/run", json={"pipelines": ["mint", "hutch_crop", "hutch_full"]})
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Metric)) > 0
    assert client.delete(f"/api/test-cases/{case['id']}").status_code == 204
    assert client.delete(f"/api/test-cases/{case['id']}").status_code == 404
    assert client.get(f"/api/test-cases/{other['id']}").status_code == 200
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PipelineRun)) == 0
        assert session.scalar(select(func.count()).select_from(Metric)) == 0
        assert session.scalar(select(func.count()).select_from(test_case_categories)) == 0
        assert session.scalar(select(func.count()).select_from(Category)) > 0
        assert session.get(Document, case["document"]["id"]) is not None
        assert session.scalar(select(AppLog).where(AppLog.event_type == "history_deleted")) is not None
    assert client.get(f"/api/documents/{case['document']['id']}/image").status_code == 200


def test_delete_rolls_back(client, case, settings, monkeypatch):
    with client.app.state.database.session_factory() as session:
        service = CaseService(session, settings, client.app.state.storage)
        def fail():
            session.flush()
            raise RuntimeError("test commit failure")
        monkeypatch.setattr(session, "commit", fail)
        with pytest.raises(RuntimeError):
            service.delete(case["id"])
    with client.app.state.database.session_factory() as session:
        assert session.get(Case, case["id"]) is not None
        assert session.scalar(select(AppLog).where(AppLog.event_type == "history_deleted")) is None


def test_log_never_accepts_secret_identifiers_or_arbitrary_payload(client, settings):
    from pydantic import SecretStr
    settings.database_url = SecretStr("postgresql://test:private-password@localhost/test")
    with client.app.state.database.session_factory() as session:
        logs = LogService(session, settings)
        logs.add("ocr_run_error", request_id=settings.model_gateway_api_key.get_secret_value(),
                 gateway_request_id="private-password", error_code="MODEL_UNAVAILABLE")
        with pytest.raises(TypeError):
            logs.add("ocr_run_error", raw_response={"image": "base64-sensitive"})
        session.commit()
    body = client.get("/api/logs").json()
    assert "private-password" not in json.dumps(body)
    assert settings.model_gateway_api_key.get_secret_value() not in json.dumps(body)
    assert body["items"][0]["request_id"] is None
    assert body["items"][0]["gateway_request_id"] is None
