import httpx
import pytest

from app.services.gt_prefill_service import prefill_pipeline
from tests.test_benchmark_pipeline import parts
from tests.test_global_layout import layout
from tests.upstream_fixture import response as upstream


def batch_response(request):
    count = sum(key == "images" for key, _ in parts(request))
    if request.url.path.endswith("text-detection-batches"):
        assert dict(request.url.params) == {"version": "6", "model": "thai_ft_v2"}
        items = [{"dt_polys": [[[2, 3], [30, 3], [30, 18], [2, 18]]], "dt_scores": [.95]} for _ in range(count)]
        return httpx.Response(200, json={"data": {"contract_version": "leaf-inference-v1", "kind": "text_detection_batch", "count": count, "result": {"results": items}}, "meta": {}})
    if request.url.path.endswith("text-recognition-batches"):
        assert dict(request.url.params) == {"version": "6", "model": "thai_ft_v1"}
        return httpx.Response(200, json={"data": {"count": count, "results": [{"text": f"draft {i}\nsecond line", "confidence": .9} for i in range(count)]}, "meta": {}})
    return upstream(request)


def official(client):
    return client.post("/api/pipelines", json={"name": "Selected official", "source": "official", "execution_mode": "integrated"}).json()["pipeline_id"]


def test_prefill_uses_exact_batches_and_stays_unconfirmed_without_extra_result(client, document, gateway):
    case, fields = layout(client, document)
    pipeline = official(client)
    gateway[0]["handler"] = batch_response
    root = f"/api/test-cases/{case['id']}"
    # The browser serializes explicit null GT values while saving a new layout.
    client.put(root + "/global-fields", json={"fields": [{**f, "ground_truth_raw": None} for f in fields], "confirmed": True})
    result = client.post(root + "/run", json={"pipelines": [pipeline]})
    assert result.status_code == 200, result.text
    assert [r["pipeline_id"] for r in result.json()["runs"]] == [pipeline]
    saved = client.get(root).json()
    assert saved["gt_prefill"]["status"] == "ready"
    assert saved["ground_truth_raw"] == "draft 0\nsecond line\ndraft 1\nsecond line"
    assert [f["id"] for f in saved["global_fields"]] == [f["id"] for f in fields]
    assert all(f["confirmed_at"] is None for f in saved["global_fields"])
    assert saved["document_gt_confirmed_at"] is None
    assert saved["runs"][0]["document_evaluation"] is None
    batches = [r for r in gateway[1] if r.url.path.endswith("-batches")]
    assert len(batches) == 2
    assert all(sum(k == "images" for k, _ in parts(r)) == 2 for r in batches)
    before_evaluation = len(gateway[1])
    evaluated = client.post(root + "/evaluate", json={"mode": "auto", "global_field_ids": [f["id"] for f in fields], "require_complete_gt": True})
    assert evaluated.status_code == 200, evaluated.text
    assert len(gateway[1]) == before_evaluation
    assert evaluated.json()["document_gt_confirmed_at"] is not None
    # Clearing the draft is an intentional edit, not permission to overwrite it on rerun.
    client.put(root + f"/global-fields/{fields[0]['id']}/ground-truth", json={"ground_truth_raw": ""})
    before = len(gateway[1])
    assert client.post(root + "/run", json={"pipelines": [pipeline]}).status_code == 200
    assert not any(r.url.path.endswith("-batches") for r in gateway[1][before:])
    assert client.get(root).json()["global_fields"][0]["ground_truth_raw"] == ""


def test_reuse_selected_matching_custom_without_duplicate_requests(client, document, gateway):
    case, _ = layout(client, document)
    with client.app.state.database.session_factory() as session:
        config = prefill_pipeline([])
        config.pipeline_id = "dynamic_selected"
        session.add(config)
        session.commit()
    gateway[0]["handler"] = batch_response
    root = f"/api/test-cases/{case['id']}"
    response = client.post(root + "/run", json={"pipelines": ["dynamic_selected"]})
    assert response.status_code == 200, response.text
    assert len(gateway[1]) == 2
    saved = client.get(root).json()
    assert saved["gt_prefill"]["status"] == "ready"
    assert len(saved["runs"]) == 1
    assert saved["ground_truth_raw"] == saved["runs"][0]["final_text"]


@pytest.mark.parametrize("confirmed", [False, True])
def test_existing_manual_draft_or_confirmed_gt_is_never_replaced(client, document, gateway, confirmed):
    case, fields = layout(client, document)
    pipeline = official(client)
    root = f"/api/test-cases/{case['id']}"
    for field in fields:
        client.put(root + f"/global-fields/{field['id']}/ground-truth", json={"ground_truth_raw": "user GT"})
    client.put(root + "/ground-truth", json={"ground_truth_raw": "user GT\nuser GT"})
    assert client.post(root + "/run", json={"pipelines": [pipeline]}).status_code == 200
    if confirmed:
        result = client.post(root + "/evaluate", json={"mode": "auto", "global_field_ids": [f["id"] for f in fields], "require_complete_gt": True})
        assert result.status_code == 200, result.text
    before = len(gateway[1])
    assert client.post(root + "/run", json={"pipelines": [pipeline]}).status_code == 200
    assert not any(r.url.path.endswith("-batches") for r in gateway[1])
    saved = client.get(root).json()
    assert saved["ground_truth_raw"] == "user GT\nuser GT"
    assert all(f["ground_truth_raw"] == "user GT" for f in saved["global_fields"])
    assert len(gateway[1]) > before


def test_failed_assistance_does_not_fail_selected_pipeline_or_retry(client, document, gateway):
    case, _ = layout(client, document, count=1)
    pipeline = official(client)
    gateway[0]["handler"] = lambda request: httpx.Response(503, json={"detail":"unavailable"}) if request.url.path.endswith("-batches") else upstream(request)
    root = f"/api/test-cases/{case['id']}"
    result = client.post(root + "/run", json={"pipelines": [pipeline]})
    assert result.status_code == 200 and result.json()["runs"][0]["status"] == "success"
    saved = client.get(root).json()
    assert saved["gt_prefill"]["status"] == "unavailable"
    assert saved["global_fields"][0]["ground_truth_raw"] is None
    before = len(gateway[1])
    client.post(root + "/run", json={"pipelines": [pipeline]})
    assert not any(r.url.path.endswith("-batches") for r in gateway[1][before:])


def test_prefill_applies_by_id_and_preserves_partial_failure_and_concurrent_edit():
    from types import SimpleNamespace as NS

    from app.services.global_layout_service import reading_lines
    from app.services.gt_prefill_service import apply_prefill

    first = NS(id="first", field_index=2, ground_truth_raw=None, confirmed_at=None)
    second = NS(id="second", field_index=1, ground_truth_raw=None, confirmed_at=None)
    case = NS(global_fields=[first, second], ground_truth_raw=None, document_gt_confirmed_at=None, gt_prefill={"status":"pending"})
    results = {"first": NS(status="success", boxes=[], final_text="A\nB"), "second": NS(status="error")}
    apply_prefill(case, results, reading_lines)
    assert case.gt_prefill["status"] == "partial"
    assert first.ground_truth_raw == "A\nB" and second.ground_truth_raw is None
    assert case.ground_truth_raw == "\nA\nB"
    first.ground_truth_raw = "user edit"
    case.ground_truth_raw = "user document"
    apply_prefill(case, results, reading_lines)
    assert first.ground_truth_raw == "user edit"
    assert case.ground_truth_raw == "user document"
