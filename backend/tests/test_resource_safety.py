import asyncio
import json
from copy import deepcopy

import httpx
import pytest

from app.core.concurrency import ordered_map
from app.integrations.batch_gateway import BatchGateway
from app.integrations.model_gateway import GatewayError, ModelGatewayClient


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_workers_are_bounded_and_keep_order(limit):
    async def scenario():
        active = peak = 0

        async def work(item):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep((8 - item) / 1000)
            active -= 1
            return item * 2

        assert await ordered_map(range(8), work, limit) == list(range(0, 16, 2))
        assert peak == limit
        assert await ordered_map([], work, limit) == []

    asyncio.run(scenario())


def test_transport_archive_is_not_retained_but_results_and_meta_are(settings, gateway):
    payload = {"data": {"contract_version": "leaf-inference-v1", "kind": "text_recognition_batch",
                        "count": 1, "results": [{"rec_text": "ทดสอบ", "rec_score": .9}],
                        "model_selection": {"version": "v6", "variant": "thai_ft_v1"},
                        "raw_output": {"logits": [0.123] * 10000}},
               "meta": {"request_id": "upstream-id", "duration_ms": 10, "service": "rec"},
               "unused_transport_tensor": [0.123] * 10000}
    original = deepcopy(payload)
    gateway[0]["handler"] = lambda _: httpx.Response(200, json=payload)
    client = ModelGatewayClient(settings)
    result = asyncio.run(client.send(client.build_batch_request(
        pngs=[b"png"], endpoint="/api/v1/text-recognition-batches", version=6, request_id="id")))
    assert set(result) == {"data", "meta"}
    assert "raw_output" not in result["data"]
    assert result["meta"] == original["meta"]
    assert result["data"]["results"] == original["data"]["results"]
    assert result["data"]["model_selection"] == original["data"]["model_selection"]


def test_model_worker_error_is_not_mislabeled_validation_and_does_not_leak(settings, gateway, caplog):
    gateway[0]["handler"] = lambda _: httpx.Response(422, json={"error": {
        "code": "UPSTREAM_MODEL_ERROR", "request_id": "worker-id",
        "message": "private OCR test-gateway-secret", "details": [
            {"type": "model_loading_error", "message": "private OCR", "input": "sensitive"},
            {"type": "test-gateway-secret", "code": "test-gateway-secret"}]}})
    client = ModelGatewayClient(settings, pipeline_id="dynamic_test")
    request = client.build_batch_request(pngs=[b"png"], endpoint="/api/v1/text-recognition-batches", version=6, request_id="ours")
    request["params"]["model"] = "thai_ft_v1"
    with pytest.raises(GatewayError) as exc:
        asyncio.run(client.send(request))
    assert exc.value.request_id == "worker-id"
    assert exc.value.details == [{"type": "model_loading_error"}]
    event = json.loads(caplog.records[-1].message)
    assert event["failure_category"] == "upstream_model"
    assert event["model_selection"] == {"version": "6", "model": "thai_ft_v1"}
    assert event["batch_count"] == 1
    assert all(s not in caplog.text + str(exc.value) for s in ["private OCR", "test-gateway-secret", "sensitive"])
    assert len(gateway[1]) == 1  # No blind retry of 422.


def test_batch_copies_only_owned_slice_and_preserves_alias_order(settings):
    class NeverCopyArchive:
        def __deepcopy__(self, memo):
            raise AssertionError("Transport archive copied")

    async def scenario():
        client = ModelGatewayClient(settings)

        async def send(request):
            items = [{"text": part[1][1].decode(), "polygon": [[1, 2]]} for part in request["files"]]
            return {"data": {"count": len(items), "results": items, "predictions": items,
                             "result": {"results": items}, "raw_output": NeverCopyArchive(),
                             "model_selection": {"version": "v5"}},
                    "meta": {"request_id": "batch-id", "duration_ms": 12}}

        client.send = send
        batches = BatchGateway()
        outputs = await asyncio.gather(*(batches.send(client, client.build_batch_request(
            pngs=[str(i).encode()], endpoint="/rec", version=5, request_id=str(i))) for i in range(3)))
        assert [x["data"]["results"][0]["text"] for x in outputs] == ["0", "1", "2"]
        for item in outputs:
            assert item["data"]["count"] == 1
            assert item["data"]["results"] is item["data"]["predictions"]
            assert item["data"]["result"]["results"] is item["data"]["results"]
            assert item["meta"]["request_id"] == "batch-id"
        outputs[0]["data"]["results"][0]["polygon"][0][0] = 99
        assert outputs[1]["data"]["results"][0]["polygon"][0][0] == 1

    asyncio.run(scenario())


def test_manager_shares_task_budget_across_fields_and_isolates_failures(settings, monkeypatch):
    from types import SimpleNamespace

    from app.pipelines.base import PipelineResult
    from app.services.pipeline_manager import PipelineManager

    active = peak = 0

    class Adapter:
        requires_crop = True

        def __init__(self, config, settings):
            self.config = config
            self.gateway = SimpleNamespace()
            self.diagnostics = {}

        async def run(self, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(.005)
                if self.config.pipeline_id == "p1":
                    raise GatewayError("worker unavailable", "UPSTREAM_MODEL_ERROR")
                return PipelineResult(self.config.pipeline_id, self.config.name, "ok", "ok", .9, 1)
            finally:
                active -= 1

    monkeypatch.setattr("app.services.pipeline_manager.DynamicDetectionRecognitionAdapter", Adapter)

    async def scenario():
        manager = PipelineManager(settings)
        configs = [SimpleNamespace(pipeline_id=f"p{i}", name=f"P{i}", source="custom", execution_mode="det_rec") for i in range(4)]
        fields = await asyncio.gather(*(manager.run(configs, None, None, None) for _ in range(3)))
        for runs in fields:
            assert [r.pipeline_id for r in runs] == ["p0", "p1", "p2", "p3"]
            assert [r.status for r in runs] == ["success", "error", "success", "success"]
        assert peak == settings.ocr_max_concurrent_tasks

    asyncio.run(scenario())
