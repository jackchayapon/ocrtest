import io
import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.core.errors import AppError
from app.services.auto_roi_service import is_text_region, layout_prediction_response


@pytest.mark.parametrize("label", ["text", "Text-Line", "paragraph", "title", "figure_caption", "page_number"])
def test_text_labels_are_retained(label):
    assert is_text_region({"label": label})


@pytest.mark.parametrize("label", ["image", "picture", "figure", "logo", "chart", "table", "formula", "unknown", 1])
def test_non_text_and_unknown_classes_are_excluded_even_in_text_mode(label):
    assert not is_text_region({"label": label, "text": "caption", "bbox": [1, 2, 3, 4]}, text_only=True)


def test_unlabelled_legacy_text_detection_is_supported_but_not_layout():
    assert is_text_region({"bbox": [1, 2, 3, 4]}, text_only=True)
    assert not is_text_region({"bbox": [1, 2, 3, 4]})
    assert not is_text_region({"label": "text", "category": "image"}, text_only=True)
    assert not is_text_region({"class_id": 2}, text_only=True)


@pytest.mark.parametrize("mode", ["text-line", "layout", "hybrid"])
def test_auto_roi_returns_only_text_regions(client, document, gateway, mode):
    gateway[0]["handler"] = lambda request: httpx.Response(200, json={"data": {"regions": [
        {"bbox": [10, 20, 100, 40], "label": "text", "score": .9},
        {"bbox": [15, 45, 110, 70], "type": "image", "score": .99},
        {"bbox": [20, 80, 120, 100], "block_label": "paragraph_title"},
        {"bbox": [25, 110, 130, 140], "category": "figure"},
    ]}, "meta": {"request_id": "text-only"}})
    response = client.post(f"/api/documents/{document['id']}/auto-rois", json={"auto_roi_mode": mode})
    assert response.status_code == 200, response.text
    regions = response.json()["regions"]
    assert len(regions) == 2
    assert [r["roi"]["y1"] for r in regions] == [20, 80]


def test_empty_raw_layout_prediction_is_a_valid_empty_result(client, document, gateway):
    # Observed with one synthetic image at the real layout-predictions endpoint.
    # No source path or real document content is retained in this fixture.
    gateway[0]["handler"] = lambda request: httpx.Response(200, json={
        "data": [{"input_path": "synthetic.png", "page_index": None, "boxes": []}],
        "meta": {"request_id": "layout-raw-contract"},
    })
    response = client.post(f"/api/documents/{document['id']}/auto-rois", json={})
    assert response.status_code == 200
    assert response.json() == {"regions": [], "request_id": "layout-raw-contract"}
    assert gateway[1][-1].url.path == "/api/v1/layout-predictions"


@pytest.mark.parametrize("mode", ["text-line", "layout", "hybrid"])
@pytest.mark.parametrize("expand", [False, True])
def test_observed_layout_predictions_keep_pixel_coordinates_and_filter_tables(client, gateway, mode, expand):
    payload = json.loads((Path(__file__).parent / "fixtures/layout_predictions.json").read_text(encoding="utf-8"))
    original = deepcopy(payload)
    gateway[0]["handler"] = lambda request: httpx.Response(200, json=payload)
    with Image.new("RGB", (1200, 1600), "white") as image, io.BytesIO() as output:
        image.save(output, format="PNG")
        uploaded = client.post("/api/documents", files={"file": ("synthetic.png", output.getvalue(), "image/png")})
    assert uploaded.status_code == 201
    response = client.post(f"/api/documents/{uploaded.json()['id']}/auto-rois",
                           json={"auto_roi_mode": mode, "expand_text_rois": expand})
    assert response.status_code == 200, response.text
    regions = response.json()["regions"]
    expected = [box for box in payload["data"][0]["boxes"] if box["label"] in {"text", "paragraph_title"}]
    assert len(regions) == len(expected) == 12
    for region, box in zip(regions, expected, strict=True):
        assert [region["roi"][key] for key in ("x1", "y1", "x2", "y2")] == box["coordinate"]
        assert region["score"] == box["score"]
        assert region["source"] == "layout-predictions"
    from tests.test_gateway_and_fairness import multipart
    parts = multipart(gateway[1][-1])
    assert parts["auto_roi_mode"] == mode.encode()
    assert parts["expand_text_rois"] == str(expand).lower().encode()
    assert payload == original


@pytest.mark.parametrize("data", [
    None, [], [{"boxes": []}, {"boxes": []}], [None], [{}], [{"boxes": None}], [{"boxes": "invalid"}],
    [{"boxes": [None]}], [{"boxes": [{"label": "text"}]}],
    [{"boxes": [{"coordinate": [1, 2, 3], "label": "text"}]}],
    [{"boxes": [{"coordinate": [1, 2, 0, 4], "label": "text"}]}],
    [{"boxes": [{"coordinate": [1, 2, 1, 4], "label": "text"}]}],
    [{"boxes": [{"coordinate": [True, 2, 3, 4], "label": "text"}]}],
    [{"boxes": [{"coordinate": [1, 2, "NaN", 4], "label": "text"}]}],
    [{"boxes": [{"coordinate": [1, 2, 3, 4], "label": 1}]}],
])
def test_malformed_raw_layout_response_fails_closed(client, document, gateway, data):
    gateway[0]["handler"] = lambda request: httpx.Response(200, json={"data": data, "meta": {}})
    response = client.post(f"/api/documents/{document['id']}/auto-rois", json={})
    assert response.status_code == 502
    assert "regions" not in response.json()


def test_raw_layout_nonfinite_coordinates_and_legacy_body_are_preserved():
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(AppError) as error:
            layout_prediction_response([{"boxes": [{"coordinate": [0, 0, value, 10], "label": "text"}]}])
        assert error.value.status_code == 502
    legacy = {"regions": [{"bbox": [1, 2, 3, 4], "label": "text"}]}
    assert layout_prediction_response(legacy) is legacy


def test_raw_layout_coordinates_use_existing_clipping_and_rounding(client, document, gateway):
    gateway[0]["handler"] = lambda request: httpx.Response(200, json={
        "data": [{"boxes": [{"coordinate": [-10.4, 20.2, 1000.5, 250.1], "label": "text", "score": None}]}],
        "meta": {},
    })
    response = client.post(f"/api/documents/{document['id']}/auto-rois", json={})
    assert response.status_code == 200
    region = response.json()["regions"][0]
    assert region["roi"] == {"x1": 0, "y1": 20, "x2": 300, "y2": 200}
    assert region["score"] is None
