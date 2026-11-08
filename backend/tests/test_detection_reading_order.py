from copy import deepcopy
from types import SimpleNamespace

import httpx

from app.services.global_layout_service import reading_lines
from app.services.global_order import ordered_detection_boxes
from tests.test_global_layout import layout


def test_same_row_vertical_jitter_keeps_text_geometry_pairs_and_raw_order():
    boxes = [
        {"bbox": [40, 10, 80, 20], "text": "right", "confidence": .8},
        {"bbox": [0, 12, 30, 22], "text": "left", "confidence": .9},
        {"bbox": [0, 30, 80, 40], "text": "next row", "confidence": .7},
    ]
    original = deepcopy(boxes)
    ordered = ordered_detection_boxes(boxes)
    assert [b["text"] for b in ordered] == ["left", "right", "next row"]
    assert ordered[0] is boxes[1] and ordered[1] is boxes[0]
    assert boxes == original
    assert reading_lines(SimpleNamespace(boxes=boxes, final_text="raw")) == ["left", "right", "next row"]


def test_row_grouping_does_not_chain_overlap_into_next_line():
    boxes = [{"bbox": bounds, "text": text} for bounds, text in [
        ([20, 0, 30, 10], "A"), ([10, 4, 20, 14], "B"), ([0, 8, 10, 18], "C"),
    ]]
    assert [b["text"] for b in ordered_detection_boxes(boxes)] == ["B", "A", "C"]
    assert reading_lines(SimpleNamespace(boxes=[], final_text="one\ntwo")) == ["one", "two"]


def test_official_saved_text_and_preview_boxes_have_same_row_order(client, document, gateway):
    case, fields = layout(client, document, count=1)
    pipeline = client.post("/api/pipelines", json={"name": "Row order", "source": "official", "execution_mode": "integrated"}).json()
    gateway[0]["handler"] = lambda request: httpx.Response(200, json={"data": {"predictions": [{
        "rec_texts": ["right", "left", "next"], "rec_scores": [.8, .9, .7],
        "rec_polys": [
            [[30, 2], [48, 2], [48, 12], [30, 12]],
            [[2, 4], [25, 4], [25, 14], [2, 14]],
            [[2, 24], [48, 24], [48, 34], [2, 34]],
        ],
    }]}, "meta": {}})
    response = client.post(f"/api/test-cases/{case['id']}/run", json={"pipelines": [pipeline["pipeline_id"]]})
    assert response.status_code == 200, response.text
    run = response.json()["runs"][0]
    assert run["status"] == "success", run
    field = run["fields"][0]
    assert field["global_field_id"] == fields[0]["id"]
    assert field["ocr_text"] == run["final_text"] == "left\nright\nnext"
    assert [b["text"] for b in field["diagnostics"]["boxes"]] == ["left", "right", "next"]
    assert field["diagnostics"]["ordering"] == "row_then_left_within_global_field"
