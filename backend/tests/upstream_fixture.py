"""Controlled HTTP fixture for tests only; never imported by application code."""

import httpx

TEXT = "บริษัท ซีดีจี จำกัด"


def response(request):
    if request.url.path.endswith("text-detection-batches"):
        return httpx.Response(200, json={"data": {
            "contract_version": "leaf-inference-v1", "kind": "text_detection_batch", "count": 1,
            "result": {"results": [{"dt_polys": [[[2, 3], [50, 3], [50, 30], [2, 30]]], "dt_scores": [0.95]}]},
        }, "meta": {"request_id": "fixture-det", "duration_ms": 100, "service": "test-only-upstream"}})
    if request.url.path.endswith("text-recognition-batches"):
        if request.url.params.get("model") == "thai_ft_v2":
            return httpx.Response(200, json={"data": {
                "contract_version": "leaf-inference-v1", "kind": "text_recognition_batch",
                "results": [{"rec_text": TEXT, "rec_score": 0.97}], "count": 1,
                "model_selection": {"version": "v6", "variant": "thai_ft_v2", "model_name": "PP-OCRv6_medium_rec"},
            }, "meta": {"request_id": "fixture-rec", "duration_ms": 20, "service": "test-only-upstream"}})
        return httpx.Response(200, json={"data": {"results": [{"text": TEXT, "confidence": 0.97}], "count": 1},
                                        "meta": {"request_id": "fixture-rec", "duration_ms": 20, "service": "test-only-upstream"}})
    if request.url.path.endswith("document-layouts"):
        from tests.test_gateway_and_fairness import multipart

        if multipart(request).get("auto_roi_mode") == b"layout":
            return httpx.Response(503, json={"error": {"code": "SERVICE_UNAVAILABLE"}})
        return httpx.Response(200, json={"data": {"regions": [
            {"bbox": [80, 225, 850, 355], "score": 0.8, "source": "test-only-upstream"},
            {"bbox": [400, 400, 850, 470], "score": 0.9, "source": "test-only-upstream"}
        ]}, "meta": {"request_id": "fixture-layout"}})
    if request.url.path.endswith(("health", "readiness")):
        return httpx.Response(200, json={"data": {"services": [
            {"name": name, "status": "ready"} for name in ("ocr-custom", "ocr-paddle", "layout")
        ]}, "meta": {}})
    polygon = [[2, 3], [50, 3], [50, 30], [2, 30]]
    if request.url.params.get("engine") == "custom":
        data = {"text": TEXT, "confidence": 0.94, "lines": [
            {"text": TEXT, "polygon": polygon, "rec_score": 0.94, "det_score": 0.95},
            {"text": "ABCD", "polygon": [[60, 3], [95, 3], [95, 30], [60, 30]], "rec_score": 0.93, "det_score": 0.95}
        ]}
    else:
        data = {"predictions": [{"rec_texts": [TEXT], "rec_scores": [0.97],
                                 "rec_polys": [polygon]}]}
    return httpx.Response(200, json={"data": data, "meta": {
        "request_id": "fixture-request", "duration_ms": 123.4,
        "service": "test-only-upstream", "model": "test-only-model",
    }})
