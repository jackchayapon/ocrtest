from app.services.evaluation_insights_service import attribute_source_fields
from app.services.evaluation_insights_service import contextual_events, EvaluationInsightsService
from app.services.metrics_service import align_errors
import pytest


@pytest.mark.parametrize("gt,ocr", [
    ("No.1234 " + "same " * 20 + "www.example.com", "No.1234 " + "same " * 20 + "www.example.c0om"),
    ("No.1234 " + "same " * 20 + "Fax: 123", "No.1234 " + "same " * 20 + "Fax:123"),
    ("ab cd ef", "aXbcd Ye"), ("abc", ""), ("", "abc"), ("a😀 b", "a😀b!"),
])
def test_excerpt_anchors_follow_alignment_not_document_start(gt, ocr):
    events = list(contextual_events(align_errors(gt, ocr), gt, ocr))
    # Reconstruct the two cursor streams: stretches between edits must be equal.
    a = b = 0
    for e in events:
        ra, rb = e["ground_truth_position"], e["ocr_position"]
        if ra is None:
            ra = a + rb - b
        if rb is None:
            rb = b + ra - a
        assert gt[a:ra] == ocr[b:rb]
        for side, unit in (("ground_truth", e["ground_truth_unit"]), ("ocr", e["ocr_unit"])):
            highlight = e[side + "_highlight"]
            text = e[side + "_excerpt"]
            assert text[highlight["start"]:highlight["start"]+highlight["length"]] == (unit or "")
        if ra > 50:
            assert "No.1234" not in e["ground_truth_excerpt"]
            assert "No.1234" not in e["ocr_excerpt"]
        a, b = ra + (e["ground_truth_unit"] is not None), rb + (e["ocr_unit"] is not None)
    assert gt[a:] == ocr[b:]


def test_character_filter_keeps_earlier_edits_in_cursor_calculation():
    gt = "first " + "middle " * 10 + "Fax: 123"
    ocr = "Xfirst " + "middle " * 10 + "Fax:123"
    scope = EvaluationInsightsService.scope(ocr, gt, None, True, "success", None, None, None, {}, " ", False, legacy=True)
    assert scope["state"] == "ready"
    assert len(scope["details"]) == 1
    detail = scope["details"][0]
    assert "Fax:123" in detail["ocr_excerpt"]
    assert detail["ocr_excerpt"][detail["ocr_highlight"]["start"]:] == "123"


def test_document_events_keep_alignment_and_map_to_source_roi():
    fields = [dict(id="a", field_index=1, roi={"x1":10}, ground_truth_raw="first\nline"),
              dict(id="b", field_index=2, roi={"x1":90}, ground_truth_raw="second")]
    predictions = [dict(global_field_id="a", ocr_text="first line"),
                   dict(global_field_id="b", ocr_text="second extra")]
    events = [dict(error_type="deletion", ground_truth_position=6, ocr_position=None),
              dict(error_type="insertion", ground_truth_position=None, ocr_position=18),
              dict(error_type="substitution", ground_truth_position=12, ocr_position=12)]
    scope = {"details": events}
    attribute_source_fields(scope, fields, predictions, "first\nline\nsecond")
    assert [e["source_field"]["id"] for e in events] == ["a", "b", "b"]
    assert events[1]["source_field"]["roi"] == {"x1":90}
    assert events[0]["ground_truth_position"] == 6


def test_unmapped_document_gt_does_not_guess_a_crop():
    fields = [dict(id="a", field_index=1, roi={}, ground_truth_raw="other")]
    scope = {"details": [dict(error_type="deletion", ground_truth_position=0, ocr_position=None)]}
    attribute_source_fields(scope, fields, [], "independent document GT")
    assert "source_field" not in scope["details"][0]


def test_whole_details_use_same_field_boundaries_and_preserve_lines():
    fields = [dict(id="a",field_index=14,roi={},ground_truth_raw="Human Resources"),
              dict(id="b",field_index=15,roi={},ground_truth_raw="Tel : (66)45\n123456"),
              dict(id="c",field_index=16,roi={},ground_truth_raw="Fax: 654321")]
    predictions = [dict(global_field_id=f["id"],ocr_text=f["ground_truth_raw"]) for f in fields]
    predictions[1]["ocr_text"] = "Tel: (66) 45\n123456"
    gt = "\n".join(f["ground_truth_raw"] for f in fields)
    ocr = "\n".join(f["ocr_text"] for f in predictions)
    scope = EvaluationInsightsService.scope(ocr,gt,None,True,"success",None,None,None,{}," ",False,legacy=True)
    attribute_source_fields(scope,fields,predictions,gt)
    assert len(scope["details"]) == 2
    for detail in scope["details"]:
        assert detail["source_field"]["id"] == "b"
        assert detail["ground_truth_excerpt"] == "Tel : (66)45\n123456"
        assert detail["ocr_excerpt"] == "Tel: (66) 45\n123456"
        assert detail["line_number"] == 1
        highlight = detail["ocr_highlight"]
        assert detail["ocr_excerpt"][highlight["start"]:highlight["start"]+highlight["length"]] == (detail["ocr_unit"] or "")


def test_default_detail_includes_errors_after_fiftieth_event():
    scope = EvaluationInsightsService.scope("b" * 60, "a" * 60, None, True, "success", None, None, None, {}, None, False, legacy=True)
    assert len(scope["details"]) == 60
    assert scope["details_truncated"] is False
