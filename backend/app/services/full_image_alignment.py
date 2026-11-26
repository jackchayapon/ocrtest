"""Confirmed correspondence; raw OCR and detector coordinates remain unchanged."""
from collections import Counter
import math
from statistics import fmean
from app.core.errors import AppError
from app.db.models import now
from app.services.spatial_comparison import compare_spatial, detection_boxes


def is_full_image(case):
    return (case.workflow == "global" and len(case.global_fields) == 1
            and case.global_fields[0].roi == dict(x1=0, y1=0,
                x2=case.page_width or case.document.width,
                y2=case.page_height or case.document.height))


def save_alignment(case, data):
    if not is_full_image(case):
        raise AppError("Alignment is available only for full-image input", 422)
    if not data.confirmed_gt:
        raise AppError("Confirm the GT correspondence before saving", 422)
    if any("\n" in r.text or "\r" in r.text for r in data.references):
        raise AppError("Each full-image GT reference must contain exactly one line", 422)
    reference = "\n".join(r.text for r in data.references)
    source = (case.ground_truth_raw or "").replace("\r\n", "\n").replace("\r", "\n")
    if Counter(r.text for r in data.references) != Counter(source.split("\n")):
        raise AppError("Save the current GT text and order before confirming correspondence", 409)
    result = compare_spatial(case, data)
    geometry_complete = bool(result["geometry_available"]) and all(r.roi for r in data.references)
    if data.text_only and geometry_complete:
        raise AppError("Text-only confirmation is available only when geometry is unavailable", 422)
    baseline = compare_spatial(case, data.model_copy(update={"overrides": [], "confirmed_gt": False}))
    if not data.text_only and baseline["geometry_available"] and len(baseline["matches"]) < len(data.references):
        locked_ids = {row["id"] for row in baseline["rows"] if row["status"] == "missing"
                      and next(r for r in data.references if r.id == row["id"]).roi is not None}
        if any(m["reference_id"] in locked_ids for m in result["matches"]):
            raise AppError("Missing Pipeline fields are locked empty placeholders and cannot be swapped", 422)
    if not data.text_only and result["ambiguous"]:
        raise AppError("Resolve ambiguous DET matches before confirming", 422)
    run = next(r for r in case.runs if str(r.id) == str(data.run_id))
    # Geometry cannot account for OCR text absent from the detector output.
    # Do not silently discard those characters or improve the score by omission.
    if not data.text_only and result["geometry_available"] and Counter("".join((run.final_text or "").split())) != Counter(
            "".join("".join(b["text"].split()) for b in detection_boxes(run))):
        raise AppError("DET text does not cover the complete OCR output; use the original comparison for this pipeline", 422)
    snapshot = dict(references=[r.model_dump() for r in data.references],
                    fixed_gt=True,
                    text_only=data.text_only,
                    padding_version=1,
                    placeholders=[dict(reference_id=row["id"], field_index=row["order"], text="", locked=True,
                        roi=next(r for r in data.references if r.id == row["id"]).model_dump()["roi"])
                        for row in result["rows"] if row["status"] == "missing"] if result["geometry_available"] else [],
                    overrides=[dict(box_id=m["id"], reference_id=m["reference_id"]) for m in result["matches"]],
                    ground_truth_raw=reference, source_ground_truth=source, confirmed_at=now().isoformat(),
                    rows=result["rows"], geometry_available=result["geometry_available"],
                    prediction="\n".join([" ".join(r["prediction"].splitlines()) for r in result["rows"]]
                        + [" ".join(m["text"].splitlines()) for m in result["matches"] if m["reference_id"] is None])
                        if result["geometry_available"] else run.final_text or "")
    confidence = {}
    for field in run.fields:
        for index, box in enumerate((field.diagnostics or {}).get("boxes", [])):
            value = box.get("confidence") if isinstance(box, dict) else None
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1:
                confidence[f"{field.id}:{index}"] = value
    groups = [[m["id"] for m in result["matches"] if m["reference_id"] == ref.id] for ref in data.references]
    groups += [[m["id"]] for m in result["matches"] if m["reference_id"] is None]
    snapshot["line_confidences"] = [fmean(confidence[key] for key in group) if group and all(key in confidence for key in group) else None for group in groups] if result["geometry_available"] else None
    if data.text_only:
        snapshot.update(prediction=run.final_text or "", placeholders=[], line_confidences=None, overrides=[])
    case.full_image_alignment = {**(case.full_image_alignment or {}), str(run.id): snapshot}
    # A changed correspondence requires explicit recalculation, never stale scores.
    run.document_evaluation = None
    run.metric_records.clear()
    for field in run.fields:
        field.evaluation = None
        field.confirmed_at = None
    return snapshot


def aligned_prediction(case, run, fallback):
    alignment = (getattr(case, "full_image_alignment", None) or {}).get(str(run.id))
    if not alignment or not is_full_image(case):
        return fallback
    if not alignment.get("fixed_gt"):
        raise AppError("Confirm Pipeline Field IDs against the fixed GT again before calculating", 409)
    if alignment["source_ground_truth"] != (case.ground_truth_raw or "").replace("\r\n", "\n").replace("\r", "\n"):
        raise AppError("GT changed; confirm the full-image correspondence again or clear it before calculating", 409)
    return alignment["prediction"]


def aligned_reference(case, run, fallback):
    alignment = (getattr(case, "full_image_alignment", None) or {}).get(str(run.id))
    return alignment["ground_truth_raw"] if alignment and is_full_image(case) else fallback


def initial_references(case, session):
    """Recover the actual GT prefill geometry, never borrow the target DET boxes."""
    from sqlalchemy import select
    from app.db.models import OCRJob
    from app.services.global_order import ordered_detection_boxes
    if not is_full_image(case):
        raise AppError("Alignment is available only for full-image input", 422)
    field_id = str(case.global_fields[0].id)
    boxes = (case.gt_prefill or {}).get("reference_boxes", {}).get(field_id, [])
    if not boxes:
        for checkpoint in session.scalars(select(OCRJob.prefill_results).where(
                OCRJob.test_case_id == case.id).order_by(OCRJob.created_at)):
            result = (checkpoint or {}).get(field_id, {})
            if result.get("status") == "success" and result.get("boxes"):
                boxes = result["boxes"]
                break
    rois = []
    width, height = case.page_width or case.document.width, case.page_height or case.document.height
    for box in ordered_detection_boxes(boxes) if boxes else []:
        bbox = box.get("bbox")
        valid = (isinstance(bbox, list) and len(bbox) == 4 and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in bbox))
        roi = dict(x1=max(0, math.floor(bbox[0])), y1=max(0, math.floor(bbox[1])),
                   x2=min(width, math.ceil(bbox[2])), y2=min(height, math.ceil(bbox[3]))) if valid else None
        if roi and (roi['x1'] >= roi['x2'] or roi['y1'] >= roi['y2']):
            roi = None
        rois.extend([roi] * len((box.get("text") or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")))
    lines = (case.ground_truth_raw or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return dict(references=[dict(id=f"gt-{i}", text=text, roi=rois[i] if i < len(rois) else None)
                           for i, text in enumerate(lines)], geometry_available=any(rois))


def review_alignments(case, session):
    """Read-only gate for all latest successful pipelines before full-image scoring."""
    from app.schemas.spatial_comparison import SpatialComparison
    if not is_full_image(case):
        return dict(ready=True, pipelines=[])
    refs = initial_references(case, session)["references"]
    latest = {r.pipeline_id: r for r in case.runs if not r.archived}
    checks = []
    for run in latest.values():
        if run.status != "success":
            continue
        boxes = detection_boxes(run)
        stored = (case.full_image_alignment or {}).get(str(run.id))
        needs_padding = 0 < len(boxes) < len(refs) and all(r["roi"] for r in refs)
        valid = bool(stored and stored.get("fixed_gt") and stored.get("references") == refs
                     and stored.get("source_ground_truth") == "\n".join(r["text"] for r in refs)
                     and (not needs_padding or stored.get("padding_version") == 1))
        overrides = stored["overrides"] if valid else [] if needs_padding else [
            dict(box_id=b["id"], reference_id=refs[i]["id"] if i < len(refs) else None) for i, b in enumerate(boxes)]
        result = compare_spatial(case, SpatialComparison(run_id=run.id, references=refs, overrides=overrides))
        unavailable = not boxes or not all(r["roi"] for r in refs)
        mismatch = sum(m["reference_id"] is not None and not any(
            c["reference_id"] == m["reference_id"] for c in m["candidates"]) for m in result["matches"])
        if unavailable:
            ready = bool(valid and stored.get("text_only"))
            reason = "text_only_confirmed" if ready else "geometry_unavailable"
        elif stored and not valid:
            ready, reason = False, "stale_alignment"
        elif mismatch or result["ambiguous"]:
            ready, reason = False, "mismatch"
        elif result["missing"] or result["extra"]:
            ready = valid
            reason = "gaps_confirmed" if ready else "confirm_gaps"
        else:
            ready, reason = True, "matched"
        checks.append(dict(run_id=str(run.id), pipeline_id=run.pipeline_id, ready=ready, reason=reason,
                           mismatch=mismatch, missing=result["missing"], extra=result["extra"], ambiguous=result["ambiguous"]))
    return dict(ready=bool(checks) and all(c["ready"] for c in checks), pipelines=checks)
