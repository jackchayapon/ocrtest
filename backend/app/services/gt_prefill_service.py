"""One-time, unconfirmed OCR assistance; never an evaluation pipeline."""
from urllib.parse import parse_qsl, urlsplit

from app.db.models import OCRModel, PipelineConfig
from app.services.metrics_service import normalize_text

DETECTION = "/api/v1/text-detection-batches?version=6&model=thai_ft_v2"
RECOGNITION = "/api/v1/text-recognition-batches?version=6&model=thai_ft_v1"


def pristine_gt(case):
    return (not case.document_gt_confirmed_at and not normalize_text(case.ground_truth_raw or "")
            and all(f.ground_truth_raw is None and not f.confirmed_at for f in case.global_fields))


def prefill_pipeline(configs):
    def same_path(model, path):
        if model is None:
            return False
        actual, expected = urlsplit(model.batch_path), urlsplit(path)
        return actual.path == expected.path and dict(parse_qsl(actual.query)) == dict(parse_qsl(expected.query))

    for config in configs:
        if (config.source == "custom" and config.execution_mode == "det_rec"
                and same_path(config.det_model, DETECTION) and same_path(config.rec_model, RECOGNITION)):
            return config
    # Transient configuration: no registry entry or PipelineRun is persisted.
    return PipelineConfig(
        pipeline_id="system_gt_prefill", name="GT draft assistance", source="custom", execution_mode="det_rec", enabled=True,
        det_model=OCRModel(name="DET v6 thai_ft_v2", kind="det", source="custom", version="6", weight="thai_ft_v2", batch_path=DETECTION, single_path=""),
        rec_model=OCRModel(name="REC v6 thai_ft_v1", kind="rec", source="custom", version="6", weight="thai_ft_v1", batch_path=RECOGNITION, single_path=""),
    )


def apply_prefill(case, results, reading_lines):
    # Check again after inference: an edit made while OCR runs must win.
    if not pristine_gt(case):
        case.gt_prefill = {**case.gt_prefill, "status": "skipped"}
        return
    filled = []
    for field in sorted(case.global_fields, key=lambda f: f.field_index):
        result = results.get(field.id)
        if result is not None and result.status == "success":
            text = "\n".join(reading_lines(result))
            if text.strip():
                field.ground_truth_raw = text
                field.ground_truth_normalized = normalize_text(text)
                filled.append(field.id)
    if filled:
        case.ground_truth_raw = "\n".join(f.ground_truth_raw or "" for f in sorted(case.global_fields, key=lambda f: f.field_index))
        case.ground_truth_normalized = normalize_text(case.ground_truth_raw)
    case.gt_prefill = {**case.gt_prefill, "status": "ready" if len(filled) == len(case.global_fields) else "partial" if filled else "unavailable", "field_ids": filled}
