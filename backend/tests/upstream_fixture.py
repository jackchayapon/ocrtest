"""Controlled HTTP fixture for tests only; never imported by application code."""

import httpx

TEXT = "บริษัท ซีดีจี จำกัด"


def response(request):
    if request.url.path.endswith("document-layouts"):
        from tests.test_gateway_and_fairness import multipart

        if multipart(request).get("auto_roi_mode") == b"layout":
            return httpx.Response(503, json={"error": {"code": "SERVICE_UNAVAILABLE"}})
        return httpx.Response(200, json={"data": {"regions": [
            {"bbox": [80, 225, 850, 355], "score": 0.8, "source": "test-only-upstream"}
        ]}, "meta": {"request_id": "fixture-layout"}})
    if request.url.path.endswith(("health", "readiness")):
        return httpx.Response(200, json={"data": {"services": [
            {"name": name, "status": "ready"} for name in ("ocr-custom", "ocr-paddle", "layout")
        ]}, "meta": {}})
    polygon = [[2, 3], [50, 3], [50, 30], [2, 30]]
    if request.url.params.get("engine") == "custom":
        data = {"text": TEXT, "confidence": 0.94, "lines": [
            {"text": TEXT, "polygon": polygon, "rec_score": 0.94, "det_score": 0.95}
        ]}
    else:
        data = {"predictions": [{"rec_texts": [TEXT], "rec_scores": [0.97],
                                 "rec_polys": [polygon]}]}
    return httpx.Response(200, json={"data": data, "meta": {
        "request_id": "fixture-request", "duration_ms": 123.4,
        "service": "test-only-upstream", "model": "test-only-model",
    }})
