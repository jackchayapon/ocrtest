"""Canonical layout/GT identities and explicitly evaluated prediction snapshots."""

import asyncio
from statistics import fmean

from app.core.errors import AppError
from app.db.models import GlobalField, Metric, OCRField, PipelineRun, now
from app.schemas.contracts import GlobalEvaluation
from app.services.field_service import compact_comparison, field_summary
from app.services.global_order import canonical_document_text, reading_order, ordered_detection_boxes
from app.services.metrics_service import normalize_text
from app.services.pipeline_manager import PipelineManager


def reading_lines(run):
    """Visual row order within ONE field; raw boxes/envelope are never mutated.

    Missing geometry falls back to upstream text lines for the entire field.
    This is deterministic line order, not semantic/table reading order.
    """
    boxes = [b for b in run.boxes if isinstance(b.get("text"), str)]
    if boxes and all(isinstance(b.get("bbox"), list) and len(b["bbox"]) == 4 for b in boxes):
        return [
            b["text"]
            for b in ordered_detection_boxes(boxes)
        ]
    return (run.final_text or "").splitlines() or [""]


class GlobalLayoutService:
    def __init__(self, cases):
        self.cases = cases
        self.repo = cases.repository
        self.session = self.repo.session

    def case(self, case_id):
        case = self.repo.test_case(case_id, for_update=True)
        if case.workflow != "global":
            raise AppError(
                "Historical cases retain their original evaluations; create a new Global Layout case",
                409,
            )
        return case

    def field(self, case, field_id):
        field = next((f for f in case.global_fields if f.id == field_id), None)
        if field is None:
            raise AppError("Global Field not found in this test case", 404)
        return field

    def layout(self, case_id, data):
        case = self.case(case_id)
        if case.layout_locked_at or case.runs:
            raise AppError(
                "Layout is immutable after OCR starts; create a new test case to change it", 409
            )
        existing = {f.id: f for f in case.global_fields}
        fields = []
        width, height = (
            case.page_width or case.document.width,
            case.page_height or case.document.height,
        )
        for item in data.fields:
            roi = item.roi.model_dump()
            roi["x2"], roi["y2"] = min(roi["x2"], width), min(roi["y2"], height)
            self.cases.images.validate_roi(roi, width, height)
            field_id = str(item.id)
            field = existing.get(field_id)
            if field is None:
                if self.session.get(GlobalField, field_id) is not None:
                    raise AppError("Global Field ID already belongs to another case", 409)
                field = GlobalField(
                    id=field_id, field_index=item.field_index, roi=roi, source=item.source
                )
            if field.roi != roi:
                field.confirmed_at = None
            field.roi, field.source = roi, item.source
            # GT belongs to this field identity, never to its display index.
            # The editor supplies it when cloning a layout into a new case.
            if "ground_truth_raw" in item.model_fields_set:
                if field.ground_truth_raw != item.ground_truth_raw:
                    field.confirmed_at = None
                field.ground_truth_raw = item.ground_truth_raw
                field.ground_truth_normalized = normalize_text(item.ground_truth_raw or "")
            fields.append(field)
        for field in list(case.global_fields):
            if field.id not in {str(i.id) for i in data.fields}:
                case.global_fields.remove(field)
        # Vacate unique indices before swapping order (including deleted fields).
        for index, field in enumerate(case.global_fields, 1):
            field.field_index = -index
        self.session.flush()
        case.global_fields = reading_order(fields)
        for index, field in enumerate(case.global_fields, 1):
            field.field_index = index
        if (case.ground_truth_raw is not None or any(f.ground_truth_raw is not None for f in fields)
                or any("ground_truth_raw" in item.model_fields_set for item in data.fields)):
            case.ground_truth_raw = "\n".join(f.ground_truth_raw or "" for f in case.global_fields)
            case.ground_truth_normalized = normalize_text(case.ground_truth_raw)
            case.document_gt_confirmed_at = None
        case.layout_confirmed_at = now() if data.confirmed else None
        case.updated_at = now()
        return self.repo.save(case)

    def save_gt(self, case_id, field_id, data):
        case = self.case(case_id)
        field = self.field(case, field_id)
        field.ground_truth_raw = data.ground_truth_raw
        field.ground_truth_normalized = normalize_text(data.ground_truth_raw)
        field.confirmed_at = None
        field.updated_at = case.updated_at = now()
        case.status = "tested" if case.runs else "draft"
        for run in case.runs:
            for prediction in run.fields:
                if prediction.global_field_id == field.id:
                    prediction.evaluation = prediction.confirmed_at = None
                    prediction.ground_truth_raw = prediction.ground_truth_normalized = None
            self.aggregate(run, case.evaluation_mode)
        return self.repo.save(case)

    @staticmethod
    def aggregate(run, mode="per_field"):
        summary = run.document_evaluation if mode == "whole_document" else field_summary(run.fields)
        valid = summary and (mode == "whole_document" or summary["confirmed_fields"])
        existing = next((m for m in run.metric_records if m.text_kind == "final"), None)
        if not valid:
            run.metric_records.clear()
        else:
            if existing is None:
                existing = Metric(text_kind="final")
                run.metric_records.append(existing)
            for key in ("cer", "wer", "exact_match"):
                setattr(existing, key, summary[key])

    def mode(self, case_id, mode):
        case = self.case(case_id)
        case.evaluation_mode = mode
        for run in case.runs:
            self.aggregate(run, mode)
        return self.repo.save(case)

    def save_document_gt(self, case_id, data):
        case = self.case(case_id)
        case.ground_truth_raw = data.ground_truth_raw
        case.ground_truth_normalized = normalize_text(data.ground_truth_raw)
        case.document_gt_confirmed_at = None
        case.updated_at = now()
        case.status = "tested" if case.runs else "draft"
        for run in case.runs:
            run.document_evaluation = None
            self.aggregate(run, case.evaluation_mode)
        return self.repo.save(case)

    def evaluate(self, case_id, data, *, persist=True):
        case = self.case(case_id)
        if data.require_complete_gt:
            fields = sorted(case.global_fields, key=lambda f: f.field_index)
            if not fields or any(not (f.ground_truth_raw or "").strip() for f in fields):
                raise AppError("กรุณากรอก Ground Truth ให้ครบทุก Field ก่อนคำนวณ", 422)
            joined = "\n".join(f.ground_truth_raw for f in fields)
            document = (case.ground_truth_raw or "").replace("\r\n", "\n").replace("\r", "\n")
            if joined.replace("\r\n", "\n").replace("\r", "\n") != document:
                raise AppError("กรุณาซิงก์ Whole Field และ Sub-fields ให้ตรงกันก่อนคำนวณ", 422)
            if data.mode != "auto" or {str(fid) for fid in data.global_field_ids} != {f.id for f in fields}:
                raise AppError("กรุณาคำนวณทั้ง Whole Field และ Sub-fields ให้ครบทุก Field", 422)
        if data.mode == "auto":
            # Data presence determines scopes; the visible editor never controls evaluation.
            selected = [self.field(case, str(fid)) for fid in data.global_field_ids]
            populated = [f.id for f in selected if f.ground_truth_normalized]
            whole = bool(case.ground_truth_normalized)
            if not whole and not populated:
                raise AppError("กรุณากรอก Ground Truth อย่างน้อย 1 รายการ", 422)
            display_mode = case.evaluation_mode
            if whole:
                self.evaluate(case_id, GlobalEvaluation(mode="whole_document"), persist=False)
            if populated:
                self.evaluate(case_id, GlobalEvaluation(mode="per_field", global_field_ids=populated), persist=False)
            case.evaluation_mode = display_mode
            for run in case.runs:
                self.aggregate(run, display_mode)
            return self.repo.save(case)
        latest = {}
        for run in case.runs:
            if not run.archived:
                latest[run.pipeline_id] = run
        stamp = now()
        if data.mode == "whole_document":
            if not case.ground_truth_normalized:
                raise AppError(
                    "Enter non-empty Whole Document Ground Truth before calculating", 422
                )
            valid = [
                r
                for r in latest.values()
                if r.status == "success"
                and {f.global_field_id for f in r.fields if f.status == "success"}
                == {f.id for f in case.global_fields}
            ]
            if not valid:
                raise AppError(
                    "Run OCR successfully for the complete layout before calculating", 409
                )
            for run in valid:
                prediction = canonical_document_text(case.global_fields, run.fields)
                run.document_evaluation = {
                    **compact_comparison(prediction, case.ground_truth_raw),
                    "mode": "whole_document",
                    "global_field_ids": [
                        f.id for f in sorted(case.global_fields, key=lambda f: f.field_index)
                    ],
                    "evaluated_at": stamp.isoformat(),
                }
            case.document_gt_confirmed_at = stamp
        else:
            selected = [self.field(case, str(field_id)) for field_id in data.global_field_ids]
            if any(not field.ground_truth_normalized for field in selected):
                raise AppError(
                    "Enter non-empty Per Field Ground Truth for every selected field", 422
                )
            # Validate the entire selection before mutating any evaluation.
            matches = {
                field.id: [
                    (run, p)
                    for run in latest.values()
                    for p in run.fields
                    if p.global_field_id == field.id and p.status == "success"
                ]
                for field in selected
            }
            if any(not matches[field.id] for field in selected):
                raise AppError(
                    "Run OCR successfully for each selected field before calculating", 409
                )
            for field in selected:
                for run, prediction in matches[field.id]:
                    prediction.ground_truth_raw = field.ground_truth_raw
                    prediction.ground_truth_normalized = field.ground_truth_normalized
                    prediction.confirmed_at = stamp
                    prediction.evaluation = {
                        **compact_comparison(prediction.ocr_text, field.ground_truth_raw),
                        "mode": "per_field",
                        "global_field_id": field.id,
                        "evaluated_at": stamp.isoformat(),
                    }
                field.confirmed_at = stamp
        case.evaluation_mode = data.mode
        for run in case.runs:
            self.aggregate(run, data.mode)
        case.status, case.updated_at = "confirmed", stamp
        return self.repo.save(case) if persist else case

    async def run(self, case_id, pipeline_ids):
        case = self.case(case_id)
        if not case.layout_confirmed_at or not case.global_fields:
            raise AppError("Confirm a non-empty Global Layout before running OCR", 409)
        configs = [self.repo.config(p) for p in pipeline_ids]
        case.layout_locked_at = now()
        self.cases.logs.add("ocr_run_started", case=case)
        self.session.commit()
        source, _, _ = self.cases.page_image(case.document, case.page_number)
        parents = {
            c.pipeline_id: PipelineRun(
                pipeline_id=c.pipeline_id,
                pipeline_name=c.name,
                status="success",
                crop_stage="global_fields",
                boxes=[],
                raw_response=None,
                fields=[],
            )
            for c in configs
        }
        raw_parts = {c.pipeline_id: [] for c in configs}
        with self.cases.images.open(source) as image:
            manager = PipelineManager(self.cases.settings)
            fields = sorted(case.global_fields, key=lambda field: field.field_index)
            # Process bounded groups; the manager combines matching DET/REC requests.
            for start in range(0, len(fields), 8):
                batch = fields[start:start + 8]
                results_by_field = await asyncio.gather(*(
                    manager.run(configs, image, self.cases.images.canonical_crop(image, field.roi), field.roi, field.source)
                    for field in batch
                ))
                for field, results in zip(batch, results_by_field):
                    for result in results:
                        parent = parents[result.pipeline_id]
                        lines = reading_lines(result)
                        trace_keys = (
                            "input_sha256",
                            "input_width",
                            "input_height",
                            "input_byte_size",
                            "input_format",
                            "crop_sha256",
                            "crop_width",
                            "crop_height",
                            "crop_stage",
                            "request_id",
                            "gateway_request_id",
                            "gateway_duration_ms",
                            "gateway_service",
                            "gateway_model",
                            "detector_model",
                            "recognizer_model",
                            "processing_time_ms",
                            "error_code",
                            "error_message",
                            "original_width",
                            "original_height",
                        )
                        diagnostics = {key: getattr(result, key) for key in trace_keys}
                        raw_parts[result.pipeline_id].append(result.raw_text if result.raw_text is not None else result.final_text or "")
                        diagnostics.update(
                            boxes=ordered_detection_boxes(result.boxes),
                            ordering="row_then_left_within_global_field",
                        )
                        parent.fields.append(
                            OCRField(
                                global_field_id=field.id,
                                field_index=field.field_index,
                                geometry={"roi": field.roi},
                                ocr_text="\n".join(lines),
                                confidence=result.confidence,
                                status=result.status,
                                diagnostics=diagnostics,
                            )
                        )
                        if result.status != "success":
                            parent.status, parent.error_code = "error", "FIELD_PIPELINE_ERROR"
                            parent.error_message = "One or more fields failed; successful field predictions remain available"
                        if parent.raw_response is None:
                            parent.raw_response = result.raw_response
        for parent in parents.values():
            parent.raw_text = "\n".join(raw_parts[parent.pipeline_id])
            parent.final_text = canonical_document_text(case.global_fields, parent.fields)
            if parent.raw_text == parent.final_text:
                parent.raw_text = None
            parent.normalized_text = normalize_text(parent.final_text)
            confidences = [f.confidence for f in parent.fields if f.confidence is not None]
            parent.confidence = fmean(confidences) if confidences else None
            parent.processing_time_ms = sum(
                f.diagnostics.get("processing_time_ms") or 0 for f in parent.fields
            )
            durations = [
                f.diagnostics["gateway_duration_ms"]
                for f in parent.fields
                if f.diagnostics.get("gateway_duration_ms") is not None
            ]
            parent.gateway_duration_ms = sum(durations) if durations else None
            case.runs.append(parent)
            self.cases.logs.add(
                "ocr_run_success" if parent.status == "success" else "ocr_run_error",
                case=case,
                run=parent,
            )
        # Explicit calculate is required even on reruns with saved GT.
        case.status, case.updated_at = "tested", now()
        self.repo.save(case)
        return list(parents.values())
