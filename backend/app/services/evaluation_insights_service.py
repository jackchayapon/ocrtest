"""Read-only reports for latest runs, with explicit eligibility and bounded exports."""

import csv
import io
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from zipfile import ZIP_DEFLATED, ZipFile

from app.core.errors import AppError
from app.repositories.evaluation_insights_repository import EvaluationInsightsRepository
from app.services.character_statistics import (
    RULES_VERSION,
    character_identity,
    character_statistics,
)
from app.services.field_service import compact_comparison
from app.services.metrics_service import normalize_text
from app.services.thai_error_explanations import explain_event, explain_events


def aggregate(scopes):
    eligible = [s for s in scopes if s["state"] == "ready"]
    totals = {
        k: sum(s["statistics"][k] for s in eligible)
        for k in ("character_edits", "substitution", "deletion", "insertion", "gt_characters")
    }
    chars, pairs = {}, Counter()
    for scope in eligible:
        for row in scope["statistics"]["characters"]:
            target = chars.setdefault(
                row["character"],
                dict(
                    **character_identity(row["character"]),
                    total=0,
                    substitution=0,
                    deletion=0,
                    insertion=0,
                ),
            )
            for key in ("total", "substitution", "deletion", "insertion"):
                target[key] += row[key]
        for p in scope["statistics"]["confusion_pairs"]:
            pairs[(p["expected"], p["predicted"])] += p["count"]
    return dict(
        **totals,
        characters=sorted(chars.values(), key=lambda r: (-r["total"], r["character"])),
        confusion_pairs=[
            dict(expected=a, predicted=b, count=n) for (a, b), n in pairs.most_common()
        ],
    )


def safe_csv(value):
    value = "" if value is None else str(value)
    # Excel may evaluate a formula after whitespace. JSON retains the exact original.
    return (
        "'" + value
        if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n"))
        else value
    )


def attribute_source_fields(scope, globals_, predictions, ground_truth):
    """Locate canonical document events without changing their alignment or counts."""
    by_id = {f["global_field_id"]: f for f in predictions}

    def ranges(key):
        chunks = [normalize_text((g.get("ground_truth_raw") if key == "gt" else
                    by_id.get(g["id"], {}).get("ocr_text")) or "") for g in globals_]
        joined = " ".join(c for c in chunks if c)
        if key == "gt" and joined != normalize_text(ground_truth or ""):
            return []  # Older independently entered document GT has no reliable field mapping.
        result, offset = [], 0
        for g, chunk in zip(globals_, chunks):
            if chunk:
                result.append((offset, offset + len(chunk), g))
                offset += len(chunk) + 1
        return result

    gt_ranges, ocr_ranges = ranges("gt"), ranges("ocr")
    for detail in scope["details"]:
        insertion = detail["error_type"] == "insertion"
        position = detail["ocr_position" if insertion else "ground_truth_position"]
        for start, end, field in ocr_ranges if insertion else gt_ranges:
            if position is not None and start <= position < end:
                detail["source_field"] = {k: field[k] for k in ("id", "field_index", "roi")}
                detail["source_field"]["ground_truth"] = field.get("ground_truth_raw") or ""
                detail["source_field"]["ocr_text"] = by_id.get(field["id"], {}).get("ocr_text") or ""
                # Keep document alignment, but show the complete paired field rather
                # than overlapping +/-32 character windows from adjacent fields.
                paired = []
                for side, spans, raw in (
                    ("ground_truth", gt_ranges, field.get("ground_truth_raw") or ""),
                    ("ocr", ocr_ranges, by_id.get(field["id"], {}).get("ocr_text") or ""),
                ):
                    span = next((s for s in spans if s[2]["id"] == field["id"]), None)
                    anchor = detail.get(side + "_anchor")
                    length = int(detail.get(side + "_unit") is not None)
                    if span is None or anchor is None or not span[0] <= anchor <= span[1] - length:
                        break
                    # Same code-point offsets as normalize_text; retain line breaks
                    # for display instead of flattening them into spaces.
                    display = re.sub(r"\s+", lambda m: "\n" if "\n" in m[0] or "\r" in m[0] else " ",
                                     unicodedata.normalize("NFC", raw)).strip()
                    paired.append((side, display, anchor - span[0], length))
                if len(paired) == 2:
                    for side, display, local, length in paired:
                        detail[side + "_excerpt"] = display
                        detail[side + "_highlight"] = {"start": local, "length": length}
                    source = paired[1] if insertion else paired[0]
                    detail["line_number"] = source[1][:source[2]].count("\n") + 1
                break


def contextual_events(events, reference, predicted):
    """Recover both alignment cursors, including the gap on a missing side.

    Canonical null positions mean no character, not position zero. Walk all
    events before filtering so previous insertions/deletions remain accounted for.
    """
    ref_cursor = pred_cursor = 0
    for event in events:
        a, b = event["ground_truth_position"], event["ocr_position"]
        if a is None:
            a = ref_cursor + (b - pred_cursor)
        if b is None:
            b = pred_cursor + (a - ref_cursor)
        ref_size = int(event["ground_truth_unit"] is not None)
        pred_size = int(event["ocr_unit"] is not None)
        ref_start, pred_start = max(0, a - 32), max(0, b - 32)
        yield dict(
            **event,
            ground_truth_anchor=a,
            ocr_anchor=b,
            ground_truth_excerpt=reference[ref_start:a + ref_size + 32],
            ocr_excerpt=predicted[pred_start:b + pred_size + 32],
            ground_truth_highlight={"start": a - ref_start, "length": ref_size},
            ocr_highlight={"start": b - pred_start, "length": pred_size},
        )
        ref_cursor, pred_cursor = a + ref_size, b + pred_size


def csv_bytes(rows, columns):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([safe_csv(row.get(k)) for k in columns])
    return output.getvalue().encode("utf-8-sig")


class EvaluationInsightsService:
    def __init__(self, session):
        self.repository = EvaluationInsightsRepository(session)

    def report(
        self,
        case_id,
        pipeline_id=None,
        field_id=None,
        mode=None,
        character=None,
        export=False,
        selection=None,
    ):
        case, runs, globals_, predictions = self.repository.read(
            case_id, pipeline_id, field_id, selection=selection
        )
        if selection:
            revision = case["updated_at"]
            if revision.tzinfo is None:
                revision = revision.replace(tzinfo=timezone.utc)
            if revision != selection.revision:
                raise AppError("ข้อมูลเปลี่ยนแล้ว กรุณาโหลดผลประเมินใหม่ก่อนส่งออก", 409)
            by_pipeline = {r["pipeline_id"]: r for r in runs}
            if set(by_pipeline) != set(selection.pipeline_ids):
                raise AppError("Pipeline ที่เลือกไม่อยู่ใน Test Case นี้", 422)
            runs = [by_pipeline[i] for i in selection.pipeline_ids]
            if [r["id"] for r in runs] != [str(i) for i in selection.run_ids]:
                raise AppError("มีผล OCR ใหม่ กรุณาโหลดผลประเมินใหม่ก่อนส่งออก", 409)
            if selection.mode == "per_field":
                by_field = {f["id"]: f for f in globals_}
                if set(by_field) != {str(i) for i in selection.field_ids}:
                    raise AppError("Field ที่เลือกไม่อยู่ใน Test Case นี้", 422)
                globals_ = [by_field[str(i)] for i in selection.field_ids]
            mode = selection.mode
        mode = mode or (
            case["evaluation_mode"] if case["workflow"] == "global" else "whole_document"
        )
        if field_id:
            mode = "per_field"
        # Bound aggregate input before alignment/JSON generation.
        size = sum(len(r["final_text"] or "") for r in runs) + len(case["ground_truth_raw"] or "")
        size += sum(
            len(f["ocr_text"] or "") + len(f["ground_truth_raw"] or "") for f in predictions
        )
        size += sum(len(f["ground_truth_raw"] or "") for f in globals_)
        if size > 200_000:
            raise AppError("Report input exceeds 200,000 characters; select a field/pipeline", 413)
        document = {k: case[k] for k in ("document_id", "filename", "page_number")}
        page_roi = dict(
            x1=0,
            y1=0,
            x2=case["page_width"] or case["width"],
            y2=case["page_height"] or case["height"],
        )
        result = dict(
            **document,
            test_case_id=case_id,
            evaluation_mode=mode,
            rules_version=RULES_VERSION,
            scope="latest non-archived run per pipeline, current case/page",
            pipelines=[],
        )
        globals_by_id = {f["id"]: f for f in globals_}
        for run in runs:
            fields = [f for f in predictions if f["pipeline_run_id"] == run["id"]]
            scopes = []
            if mode == "whole_document":
                if case["workflow"] == "global":
                    by_id = {f["global_field_id"]: f for f in fields}
                    prediction = "\n".join(
                        by_id.get(g["id"], {}).get("ocr_text", "") for g in globals_
                    )
                    complete = set(by_id) == set(globals_by_id) and all(
                        f["status"] == "success" for f in fields
                    )
                    confirmed = case["document_gt_confirmed_at"] and complete
                    snapshot = run["document_evaluation"]
                else:
                    prediction = run["final_text"] or ""
                    confirmed = (
                        case["status"] == "confirmed" and case["ground_truth_raw"] is not None
                    )
                    snapshot = None
                scopes.append(
                    self.scope(
                        prediction,
                        case["ground_truth_raw"],
                        snapshot,
                        confirmed,
                        run["status"],
                        None,
                        None,
                        None,
                        run["roi"] or case["roi"] or page_roi,
                        character,
                        export,
                        legacy=case["workflow"] != "global",
                    )
                )
                if case["workflow"] == "global":
                    attribute_source_fields(scopes[-1], globals_, fields, case["ground_truth_raw"])
            else:
                for f in fields:
                    g = globals_by_id.get(f["global_field_id"])
                    gt = g["ground_truth_raw"] if g else f["ground_truth_raw"]
                    confirmed = f["confirmed_at"] and (not g or g["confirmed_at"])
                    fresh = not g or normalize_text(gt or "") == normalize_text(
                        f["ground_truth_raw"] or ""
                    )
                    scope = self.scope(
                        f["ocr_text"],
                        gt,
                        f["evaluation"],
                        confirmed and fresh,
                        f["status"],
                        f["id"],
                        f["global_field_id"],
                        g["field_index"] if g else f["field_index"],
                        g["roi"] if g else case["roi"] or page_roi,
                        character,
                        export,
                    )
                    scope["confidence"] = f["confidence"]
                    scopes.append(scope)
                present = {f["global_field_id"] for f in fields}
                for g in globals_:
                    if g["id"] not in present:
                        missing = self.scope(
                            "",
                            g["ground_truth_raw"],
                            None,
                            False,
                            "error",
                            None,
                            g["id"],
                            g["field_index"],
                            g["roi"],
                            character,
                            export,
                        )
                        missing["state"] = (
                            "pipeline_failed" if run["status"] == "error" else "no_prediction"
                        )
                        if export and g["confirmed_at"]:
                            missing["confirmed_ground_truth"] = g["ground_truth_raw"]
                        scopes.append(missing)
                if selection:
                    positions = {str(i): n for n, i in enumerate(selection.field_ids)}
                    scopes.sort(key=lambda s: positions.get(s["global_field_id"], len(positions)))
            total = aggregate(scopes)
            eligible = [s for s in scopes if s["state"] == "ready"]
            chars = total["gt_characters"]
            words = sum(s["metrics"].get("gt_words", 0) for s in eligible)
            edits = sum(s["metrics"].get("word_edits", 0) for s in eligible)
            metrics = dict(
                cer=(
                    total["character_edits"] / chars
                    if chars
                    else float(bool(total["character_edits"]))
                )
                if eligible
                else None,
                wer=(edits / words if words else float(bool(edits))) if eligible else None,
                exact_match=all(s["metrics"]["exact_match"] for s in eligible)
                if eligible
                else None,
            )
            result["pipelines"].append(
                dict(
                    run_id=run["id"],
                    pipeline_id=run["pipeline_id"],
                    pipeline_name=run["pipeline_name"],
                    status=run["status"],
                    confidence=run["confidence"],
                    processing_time_ms=run["processing_time_ms"],
                    statistics=total,
                    metrics=metrics,
                    evaluation_status="complete"
                    if eligible and len(eligible) == len(scopes)
                    else "partial"
                    if eligible
                    else "not_evaluated",
                    evaluated_scopes=len(eligible),
                    total_scopes=len(scopes),
                    scopes=scopes,
                )
            )
        return result

    @staticmethod
    def scope(
        prediction,
        gt,
        snapshot,
        confirmed,
        status,
        field_id,
        global_id,
        index,
        roi,
        character,
        export,
        legacy=False,
    ):
        scope = dict(
            field_id=field_id,
            global_field_id=global_id,
            field_index=index,
            roi=roi,
            state="ready",
            metrics=None,
            statistics=None,
            details=[],
            details_truncated=False,
            line_attribution="single-line only; multiline attribution unavailable",
        )
        if export:
            scope.update(ocr_text=prediction, confirmed_ground_truth=gt if confirmed else None)
        if status != "success":
            scope["state"] = "pipeline_failed"
        elif not confirmed:
            scope["state"] = "no_confirmed_gt"
        elif not snapshot and not legacy:
            scope["state"] = "outdated"
        if scope["state"] != "ready":
            return scope
        scope["display_ground_truth"] = gt or ""
        scope["display_ocr_text"] = prediction or ""
        stats = character_statistics(prediction, gt or "")
        metrics = snapshot or compact_comparison(prediction, gt or "")
        if any(metrics.get(k) != stats[k] for k in ("character_edits", "gt_characters")):
            scope["state"] = "alignment_unavailable"
            return scope
        scope["metrics"] = {
            k: metrics.get(k) for k in ("cer", "wer", "exact_match", "word_edits", "gt_words")
        }
        scope["statistics"] = {k: v for k, v in stats.items() if k != "events"}
        scope["explanations"] = explain_events(stats["events"])
        reference, predicted = normalize_text(gt or ""), normalize_text(prediction)
        filtered = [
            e
            for e in contextual_events(stats["events"], reference, predicted)
            if character is None
            or (e["ocr_unit"] if e["error_type"] == "insertion" else e["ground_truth_unit"])
            == character
        ]
        limit = len(filtered)
        for event in filtered[:limit]:
            scope["details"].append(
                dict(
                    **event,
                    explanation=explain_event(
                        event["error_type"], event["ground_truth_unit"], event["ocr_unit"]
                    ),
                    line_number=1 if "\n" not in (gt or "") and "\n" not in prediction else None,
                )
            )
        scope["details_truncated"] = len(filtered) > limit
        if export:
            scope.update(ocr_text=prediction, confirmed_ground_truth=gt)
        return scope

    def export(self, case_id, mode=None):
        report = self.report(case_id, mode=mode, export=True)
        report["exported_at"] = datetime.now(timezone.utc).isoformat()
        # Bound uncompressed data as well as compressed ZIP. No source images/vendor envelope.
        raw = json.dumps(report, ensure_ascii=False).encode("utf-8")
        if len(raw) > 16 * 1024 * 1024:
            raise AppError("Evaluation report exceeds 16 MiB", 413)
        pipeline_rows, character_rows = [], []
        for run in report["pipelines"]:
            for scope in run["scopes"] or [dict(state="no_fields")]:
                pipeline_rows.append(
                    dict(
                        pipeline_id=run["pipeline_id"],
                        pipeline_name=run["pipeline_name"],
                        run_id=run["run_id"],
                        run_status=run["status"],
                        field_id=scope.get("field_id"),
                        global_field_id=scope.get("global_field_id"),
                        field_index=scope.get("field_index"),
                        evaluation_state=scope["state"],
                        ocr_text=scope.get("ocr_text"),
                        confirmed_ground_truth=scope.get("confirmed_ground_truth"),
                        confidence=scope.get("confidence", run["confidence"]),
                        processing_time_ms=run["processing_time_ms"],
                        **(scope.get("metrics") or {}),
                    )
                )
            for row in run["statistics"]["characters"]:
                character_rows.append(
                    dict(
                        pipeline_id=run["pipeline_id"],
                        run_id=run["run_id"],
                        **row,
                        confusion_pairs=json.dumps(
                            [
                                p
                                for p in run["statistics"]["confusion_pairs"]
                                if p["expected"] == row["character"]
                            ],
                            ensure_ascii=False,
                        ),
                    )
                )
        output = io.BytesIO()
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            summary = {
                **report,
                "pipelines": [
                    {k: v for k, v in r.items() if k != "scopes"} for r in report["pipelines"]
                ],
            }
            archive.writestr(
                "summary.json", json.dumps(summary, ensure_ascii=False).encode("utf-8")
            )
            archive.writestr("error_details.json", raw)
            archive.writestr(
                "pipeline_results.csv",
                csv_bytes(
                    pipeline_rows,
                    [
                        "pipeline_id",
                        "pipeline_name",
                        "run_id",
                        "run_status",
                        "global_field_id",
                        "field_id",
                        "field_index",
                        "evaluation_state",
                        "ocr_text",
                        "confirmed_ground_truth",
                        "confidence",
                        "cer",
                        "wer",
                        "exact_match",
                        "processing_time_ms",
                    ],
                ),
            )
            archive.writestr(
                "character_errors.csv",
                csv_bytes(
                    character_rows,
                    [
                        "pipeline_id",
                        "run_id",
                        "character",
                        "code_point",
                        "name",
                        "substitution",
                        "deletion",
                        "insertion",
                        "total",
                        "confusion_pairs",
                    ],
                ),
            )
            archive.writestr(
                "README.txt",
                (
                    "OCRLab Evaluation Report\nScope: one test case/page, latest non-archived run per pipeline, including UI-hidden pipelines.\n"
                    "Only the selected evaluation mode contributes to totals; unavailable/outdated scopes are explicit.\n"
                    "Substitutions/deletions belong to GT characters; insertions belong to OCR characters.\n"
                    "NFC + collapsed whitespace; Unicode code-point CER; Thai newmm WER. Rules: "
                    + RULES_VERSION
                    + "\nCSV is UTF-8 BOM and formula cells are prefixed with an apostrophe; exact strings are retained in JSON.\n"
                    "Line attribution is unavailable for multiline text. ROI is a field/page region, not character geometry.\n"
                    "No images, secrets or raw Gateway responses. No OCR execution or database writes.\n"
                ).encode("utf-8"),
            )
        return output.getvalue()
