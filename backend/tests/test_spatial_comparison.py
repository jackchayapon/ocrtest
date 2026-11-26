from types import SimpleNamespace as NS
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.schemas.spatial_comparison import SpatialComparison
from app.services.spatial_comparison import compare_spatial


def fixture(boxes, text="B\nA"):
    run_id = str(uuid4())
    run = NS(id=run_id, status="success", archived=False, final_text=text,
             fields=[NS(id="field", field_index=1, diagnostics={"boxes": boxes})])
    case = NS(runs=[run], page_width=None, page_height=None, document=NS(width=200, height=200))
    data = dict(run_id=run_id, confirmed_gt=True, references=[
        dict(id="a", text="A", roi=dict(x1=0, y1=0, x2=100, y2=20)),
        dict(id="b", text="B", roi=dict(x1=0, y1=40, x2=100, y2=60)),
    ])
    return case, data


def test_position_matching_ignores_text_and_detects_swapped_order():
    case, data = fixture([dict(bbox=[0, 40, 100, 60], text="B"), dict(bbox=[0, 0, 100, 20], text="A")])
    result = compare_spatial(case, SpatialComparison(**data))
    assert result["order_complete"]
    assert result["rows"][0]["model_orders"] == [2]
    assert result["rows"][1]["model_orders"] == [1]
    assert len(result["inversions"]) == 1
    assert result["stored_order_metrics"]["cer"] > 0
    assert result["spatial_metrics"]["cer"] == 0
    # Wrong text must not move the geometric match to another field.
    case.runs[0].fields[0].diagnostics["boxes"][0]["text"] = "A"
    result = compare_spatial(case, SpatialComparison(**data))
    assert result["matches"][0]["reference_id"] == "b"


def test_split_missing_extra_and_merged_boxes_are_not_silently_discarded():
    case, data = fixture([dict(bbox=[0, 0, 40, 20], text="A"), dict(bbox=[50, 0, 100, 20], text="C"),
                          dict(bbox=[0, 100, 100, 120], text="extra")])
    result = compare_spatial(case, SpatialComparison(**data))
    assert result["rows"][0]["status"] == "split"
    assert result["missing"] == result["extra"] == 1
    assert not result["order_complete"]
    assert result["spatial_metrics"]["cer"] > 0
    case.runs[0].fields[0].diagnostics["boxes"] = [dict(bbox=[0, 0, 100, 60], text="A B")]
    result = compare_spatial(case, SpatialComparison(**data))
    assert result["ambiguous"] == 1
    assert result["spatial_metrics"] is None
    assert all(row["metrics"] is None for row in result["rows"])
    data["overrides"] = [dict(box_id="field:0", reference_id="a")]
    result = compare_spatial(case, SpatialComparison(**data))
    assert result["ambiguous"] == 0 and result["missing"] == 1
    assert result["matches"][0]["status"] == "manual"


def test_no_geometry_and_unconfirmed_reference_do_not_claim_spatial_scores():
    case, data = fixture([])
    result = compare_spatial(case, SpatialComparison(**data))
    assert not result["geometry_available"] and not result["order_complete"]
    assert result["spatial_metrics"] is None
    assert result["stored_order_metrics"] is not None
    data["confirmed_gt"] = False
    result = compare_spatial(case, SpatialComparison(**data))
    assert result["stored_order_metrics"] is None


def test_run_ownership_bounds_and_override_ids_are_validated():
    case, data = fixture([])
    with pytest.raises(AppError):
        compare_spatial(case, SpatialComparison(**{**data, "run_id": uuid4()}))
    with pytest.raises(AppError):
        compare_spatial(case, SpatialComparison(**{**data, "overrides": [dict(box_id="other", reference_id="a")]}))
    data["references"][0]["roi"]["x2"] = 201
    with pytest.raises(AppError):
        compare_spatial(case, SpatialComparison(**data))


def test_api_is_read_only_and_uses_saved_results(client, document, registered_catalog, gateway):
    from tests.test_global_layout import layout, run
    case, _fields = layout(client, document, count=1, prefill=False)
    runs = run(client, case)
    root = f"/api/test-cases/{case['id']}"
    before = client.get(root).json()
    calls = len(gateway[1])
    response = client.post(root + '/spatial-comparison', json={
        "run_id": runs[0]['id'], "references": [dict(id="reference", text="manual GT",
          roi=dict(x1=0, y1=0, x2=document['width'], y2=document['height']))], "confirmed_gt": True,
    })
    assert response.status_code == 200, response.text
    assert client.get(root).json() == before
    assert len(gateway[1]) == calls
