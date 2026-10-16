import httpx
import pytest

from tests.test_benchmark_pipeline import parts
from tests.test_global_layout import layout


@pytest.mark.parametrize("mode", ["det_rec", "rec"])
@pytest.mark.parametrize("contract", ["legacy", "leaf_aliases"])
def test_global_crops_are_batched_and_results_keep_field_identity(client, document, gateway, mode, contract):
    case, fields = layout(client, document, count=3)
    models = client.get("/api/pipelines/models").json()
    selected = {kind: next(m["id"] for m in models if m["kind"] == kind and m["source"] == "custom" and m["version"] == "5" and m["weight"] == "baseline") for kind in ("det", "rec")}
    response = client.post("/api/pipelines", json={"name": "Batch test", "source": "custom", "execution_mode": mode, "det_model_id": selected["det"] if mode == "det_rec" else None, "rec_model_id": selected["rec"]})
    assert response.status_code == 201, response.text
    sizes = []

    def upstream(request):
        count = sum(key == "images" for key, _ in parts(request))
        # GT assistance uses a separate model batch; measure the selected baseline.
        if request.url.params.get("model", "baseline") == "baseline":
            sizes.append(count)
        if "detection" in request.url.path:
            data = {"contract_version": "leaf-inference-v1", "kind": "text_detection_batch", "count": count, "result": {"results": [{"dt_polys": [[[2, 3], [50, 3], [50, 30], [2, 30]]], "dt_scores": [.95]} for _ in range(count)]}}
        else:
            data = {"count": count, "results": [{"text": f"field-{i}", "confidence": .9} for i in range(count)]}
        if contract == "leaf_aliases":
            detection = "detection" in request.url.path
            items = data["result"]["results"] if detection else [{"rec_text": f"field-{i}", "rec_score": .9} for i in range(count)]
            data = {"contract_version": "leaf-inference-v1", "kind": "text_detection_batch" if detection else "text_recognition_batch", "count": count,
                    "result": {"results": items}, "results": items, "predictions": items, "raw_output": items}
        return httpx.Response(200, json={"data": data, "meta": {"duration_ms": 90}})

    gateway[0]["handler"] = upstream
    response = client.post(f"/api/test-cases/{case['id']}/run", json={"pipelines": [response.json()["pipeline_id"]]})
    assert response.status_code == 200, response.text
    result = response.json()["runs"][0]
    assert result["status"] == "success", result
    assert sizes == ([3, 3] if mode == "det_rec" else [3])
    assert [f["global_field_id"] for f in result["fields"]] == [f["id"] for f in fields]
    assert [f["ocr_text"] for f in result["fields"]] == ["field-0", "field-1", "field-2"]
    root = f"/api/test-cases/{case['id']}"
    for i, field in enumerate(fields):
        saved = client.put(root + f"/global-fields/{field['id']}/ground-truth", json={"ground_truth_raw": f"field-{i}"})
        assert saved.status_code == 200, saved.text
    saved = client.put(root + "/ground-truth", json={"ground_truth_raw": "field-0\nfield-1\nfield-2"})
    assert saved.status_code == 200, saved.text
    evaluated = client.post(root + "/evaluate", json={"mode": "auto", "global_field_ids": [f["id"] for f in fields], "require_complete_gt": True})
    assert evaluated.status_code == 200, evaluated.text
    evaluated_run = evaluated.json()["runs"][0]
    assert evaluated_run["document_evaluation"]["exact_match"]
    assert all(field["evaluation"]["exact_match"] for field in evaluated_run["fields"])
    if mode == "det_rec":
        for field, prediction in zip(fields, result["fields"]):
            assert prediction["diagnostics"]["boxes"][0]["bbox"][0] == field["roi"]["x1"] + 2


def test_batch_split_bound_and_count_mismatch(settings):
    import asyncio
    from app.integrations.batch_gateway import BatchGateway
    from app.integrations.model_gateway import ModelGatewayClient, GatewayError

    async def scenario():
        gateway = ModelGatewayClient(settings)
        sizes = []
        async def send(request):
            sizes.append(len(request["files"]))
            return {"data": {"count": 0, "results": []}, "meta": {}}
        gateway.send = send
        batches = BatchGateway()
        results = await asyncio.gather(*(batches.send(gateway, gateway.build_batch_request(pngs=[b"png"], endpoint="/rec", version=5, request_id=str(i))) for i in range(31)), return_exceptions=True)
        assert sizes == [30]
        assert all(isinstance(result, GatewayError) for result in results)
    asyncio.run(scenario())


def test_large_batch_preserves_order_across_chunks_and_query_groups(settings):
    import asyncio
    from app.integrations.batch_gateway import BatchGateway
    from app.integrations.model_gateway import ModelGatewayClient

    async def scenario():
        gateway = ModelGatewayClient(settings)
        calls = []
        async def send(request):
            calls.append((request["params"]["version"], len(request["files"])))
            return {"data": {"count": len(request["files"]), "results": [{"text": part[1][1].decode()} for part in request["files"]]}, "meta": {"duration_ms": 10}}
        gateway.send = send
        batches = BatchGateway()
        responses = await asyncio.gather(*(batches.send(gateway, gateway.build_batch_request(pngs=[str(i).encode()], endpoint="/rec", version=5 if i < 61 else 6, request_id=str(i))) for i in range(63)))
        assert sorted(calls) == [("5", 1), ("5", 30), ("5", 30), ("6", 2)]
        assert [r["data"]["results"][0]["text"] for r in responses] == [str(i) for i in range(63)]
    asyncio.run(scenario())
