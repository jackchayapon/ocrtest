"""Read-only geometric comparison. Never reorder persisted OCR or overwrite GT."""
import math

from app.core.errors import AppError
from app.services.field_service import compact_comparison


def detection_boxes(run):
    boxes = []
    for field in sorted(run.fields, key=lambda f: f.field_index):
        for index, raw in enumerate((field.diagnostics or {}).get("boxes", [])):
            bbox = raw.get("bbox") if isinstance(raw, dict) else None
            if (not isinstance(bbox, list) or len(bbox) != 4
                    or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in bbox)
                    or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]):
                continue
            boxes.append(dict(id=f"{field.id}:{index}", bbox=bbox, text=raw.get("text") or "",
                              order=len(boxes) + 1))
    return boxes


def overlap(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    small = min((a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1]))
    return intersection / small if small > 0 else 0


def compare_spatial(case, data):
    run = next((r for r in case.runs if str(r.id) == str(data.run_id) and not r.archived), None)
    if run is None:
        raise AppError("Pipeline run not found in this test case", 404)
    if run.status != "success":
        raise AppError("Choose a successful OCR run", 422)
    width, height = case.page_width or case.document.width, case.page_height or case.document.height
    refs = data.references
    if any(r.roi and (r.roi.x2 > width or r.roi.y2 > height) for r in refs):
        raise AppError("Reference box exceeds image bounds", 422)
    boxes = detection_boxes(run)
    if len(boxes) > 128 or sum(len(b["text"]) for b in boxes) > 32768:
        raise AppError("Spatial comparison exceeds document limits", 422)
    ref_ids, box_ids = {r.id for r in refs}, {b["id"] for b in boxes}
    if any(o.box_id not in box_ids or o.reference_id is not None and o.reference_id not in ref_ids for o in data.overrides):
        raise AppError("Unknown box or reference in override", 422)
    overrides = {o.box_id: o.reference_id for o in data.overrides}
    groups = {r.id: [] for r in refs}
    matches = []
    for box in boxes:
        candidates = [dict(reference_id=r.id, overlap=overlap(box["bbox"], list(r.roi.model_dump().values()))) for r in refs if r.roi]
        candidates = sorted((c for c in candidates if c["overlap"] >= .5), key=lambda c: -c["overlap"])
        manual = box["id"] in overrides
        target = overrides[box["id"]] if manual else candidates[0]["reference_id"] if len(candidates) == 1 else None
        status = "manual" if manual and target else "extra" if manual or not candidates else "ambiguous" if len(candidates) > 1 else "matched"
        matches.append({**box, "reference_id": target, "status": status, "candidates": candidates})
        if target:
            groups[target].append(box)
    ambiguous = [m for m in matches if m["status"] == "ambiguous"]
    extras = [m for m in matches if m["status"] == "extra"]
    unresolved_refs = {c["reference_id"] for m in ambiguous for c in m["candidates"]}
    rows = []
    for index, ref in enumerate(refs):
        group = groups[ref.id]
        # Reading order within a split reference is retained, not text-matched.
        prediction = " ".join(b["text"] for b in group)
        status = "ambiguous" if ref.id in unresolved_refs else "missing" if not group else "split" if len(group) > 1 else "matched"
        rows.append(dict(id=ref.id, order=index+1, ground_truth=ref.text, prediction=prediction,
                         model_orders=[b["order"] for b in group], status=status,
                         metrics=compact_comparison(prediction, ref.text) if data.confirmed_gt and status != "ambiguous" and boxes else None))
    ranks = {r.id: index for index, r in enumerate(refs)}
    ordered = [m for m in matches if m["reference_id"] is not None]
    inversions = [dict(first=a["id"], second=b["id"], first_order=a["order"], second_order=b["order"])
                  for i, a in enumerate(ordered) for b in ordered[i+1:]
                  if ranks[a["reference_id"]] > ranks[b["reference_id"]]]
    reference = "\n".join(r.text for r in refs)
    # Count extras as insertions; exclude unresolved comparisons rather than inventing matches.
    positioned = "\n".join([r["prediction"] for r in rows] + [m["text"] for m in extras])
    return dict(run_id=str(run.id), geometry_available=bool(boxes), rows=rows, matches=matches,
                inversions=inversions, order_complete=bool(boxes) and not ambiguous and not extras and all(groups.values()),
                missing=sum(r["status"] == "missing" for r in rows), extra=len(extras), ambiguous=len(ambiguous),
                stored_order_metrics=compact_comparison(run.final_text or "", reference) if data.confirmed_gt else None,
                spatial_metrics=compact_comparison(positioned, reference) if data.confirmed_gt and boxes and not ambiguous else None,
                gt_confirmed=data.confirmed_gt,
                order_source="stored_ocr_order", overlap_threshold=.5)
