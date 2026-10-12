"""Read-only reports for latest runs, with explicit eligibility and bounded exports."""

import csv
import io
import json
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
        self, case_id, pipeline_id=None, field_id=None, mode=None, character=None, export=False
    ):
        case, runs, globals_, predictions = self.repository.read(case_id, pipeline_id, field_id)
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
                        f["status"] if run["status"] == "success" else "error",
                        f["id"],
                        f["global_field_id"],
                        g["field_index"] if g else f["field_index"],
                        g["roi"] if g else case["roi"] or page_roi,
                        character,
                        export,
                    )
                    scope["confidence"] = f["confidence"]
                    scopes.append(scope)
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
        stats = character_statistics(prediction, gt or "")
        metrics = snapshot or compact_comparison(prediction, gt or "")
        if any(metrics.get(k) != stats[k] for k in ("character_edits", "gt_characters")):
            scope["state"] = "alignment_unavailable"
            return scope
        scope["metrics"] = {
            k: metrics.get(k) for k in ("cer", "wer", "exact_match", "word_edits", "gt_words")
        }
        scope["statistics"] = {k: v for k, v in stats.items() if k != "events"}
        reference, predicted = normalize_text(gt or ""), normalize_text(prediction)
        filtered = [
            e
            for e in stats["events"]
            if character is None
            or (e["ocr_unit"] if e["error_type"] == "insertion" else e["ground_truth_unit"])
            == character
        ]
        limit = len(filtered) if export else 50
        for event in filtered[:limit]:
            a, b = event["ground_truth_position"], event["ocr_position"]
            scope["details"].append(
                dict(
                    **event,
                    line_number=1 if "\n" not in (gt or "") and "\n" not in prediction else None,
                    ground_truth_excerpt=reference[max(0, (a or 0) - 32) : (a or 0) + 33],
                    ocr_excerpt=predicted[max(0, (b or 0) - 32) : (b or 0) + 33],
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
