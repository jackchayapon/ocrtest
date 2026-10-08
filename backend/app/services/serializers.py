from datetime import timezone

from app.services.field_service import compare_field, field_summary
from app.services.global_order import canonical_document_text


def field_json(field, detail=False, *, summary=False):
    evaluation = field.evaluation
    if detail and evaluation:
        evaluation = {**evaluation, **compare_field(field.ocr_text or "", field.ground_truth_raw or "")}
    return {"id": field.id, "pipeline_run_id": field.pipeline_run_id,
            "global_field_id": field.global_field_id, "status": field.status,
            "diagnostics": None if summary else field.diagnostics,
            "field_index": field.field_index, "geometry": field.geometry,
            "ocr_text": field.ocr_text, "confidence": field.confidence,
            "ground_truth_raw": field.ground_truth_raw,
            "ground_truth_normalized": field.ground_truth_normalized,
            "confirmed_at": timestamp(field.confirmed_at) if field.confirmed_at else None,
            "evaluation": evaluation}


def global_field_json(field):
    return {
        "id": field.id, "field_index": field.field_index, "roi": field.roi, "source": field.source,
        "ground_truth_raw": field.ground_truth_raw,
        "ground_truth_normalized": field.ground_truth_normalized,
        "confirmed_at": timestamp(field.confirmed_at) if field.confirmed_at else None,

    }


def timestamp(value):
    return (
        value.replace(tzinfo=timezone.utc).isoformat()
        if value.tzinfo is None
        else value.isoformat()
    )


def document_json(record, page_number=None, page_size=None):
    selected = page_number or (1 if record.document_type == "pdf" else None)
    return {
        "id": record.id,
        "filename": record.filename,
        "mime_type": record.mime_type,
        "width": page_size[0] if page_size else record.width,
        "height": page_size[1] if page_size else record.height,
        "document_type": record.document_type,
        "document_type_id": record.document_type_id,
        "document_type_name": record.business_type.name if record.business_type else None,
        "page_count": record.page_count,
        "pdf_render_dpi": record.pdf_render_dpi,
        "page_number": selected,
        "sha256": record.sha256,
        "storage_key": record.storage_key,
        "created_at": timestamp(record.created_at),
        "image_url": f"/api/documents/{record.id}/pages/{selected}/image"
        if selected
        else f"/api/documents/{record.id}/image",
    }


def category_json(record):
    return {"id": record.id, "code": record.code, "display_name": record.display_name}


def metrics_json(record):
    return {"cer": record.cer, "wer": record.wer, "exact_match": record.exact_match}


def run_json(record, detail=False, *, summary=False):
    fields = (
        "id",
        "pipeline_id",
        "pipeline_name",
        "status",
        "raw_text",
        "final_text",
        "normalized_text",
        "confidence",
        "processing_time_ms",
        "boxes",
        "raw_response",
        "document_evaluation",
        "error_message",
        "error_code",
        "input_sha256",
        "input_width",
        "input_height",
        "request_id",
        "gateway_request_id",
        "gateway_duration_ms",
        "gateway_service",
        "gateway_model",
        "detector_model",
        "recognizer_model",
        "original_width",
        "original_height",
        "roi",
        "crop_width",
        "crop_height",
        "crop_sha256",
        "input_byte_size",
        "input_format",
        "crop_stage",
    )
    data = {key: getattr(record, key) for key in fields if not summary or key not in {"boxes", "raw_response"}}
    if summary:
        data.update(boxes=[], raw_response=None)
    data["raw_text"] = record.raw_text if record.raw_text is not None else record.final_text
    if detail and record.document_evaluation:
        case = record.test_case
        prediction = canonical_document_text(case.global_fields, record.fields)
        data["document_evaluation"] = {**record.document_evaluation,
            **compare_field(prediction, case.ground_truth_raw or ""),
            "prediction": prediction, "ground_truth_raw": case.ground_truth_raw}
    metrics = {item.text_kind: metrics_json(item) for item in record.metric_records}
    return {
        **data,
        "model_info": {
            "detector": record.detector_model,
            "recognizer": record.recognizer_model,
            "service": record.gateway_service,
            "gateway_model": record.gateway_model,
        },
        "text": record.final_text,
        "created_at": timestamp(record.created_at),
        "metrics": metrics.get("final"),
        "raw_metrics": metrics.get("raw"),
        "fields": [field_json(field, detail, summary=summary) for field in record.fields],
        "field_summary": field_summary(record.fields),
    }


def history_status(record):
    latest = {r.pipeline_id: r for r in record.runs if not r.archived}
    if not latest:
        return "pending"
    successes = [r for r in latest.values() if r.status == "success"]
    if not successes:
        return "error"
    if len(successes) != len(latest):
        return "partial"
    evaluated = any(r.document_evaluation or any(f.evaluation for f in r.fields) or (record.ground_truth_raw is not None and r.metric_records) for r in successes)
    return "success" if evaluated else "no_gt"


def test_case_json(record, detail=False, *, summary=False):
    return {
        "id": record.id,
        "document_id": record.document_id,
        "document": document_json(
            record.document,
            record.page_number,
            (record.page_width, record.page_height) if record.page_number else None,
        ),
        "page_number": record.page_number,
        "roi": record.roi,
        "roi_source": record.roi_source,
        "workflow": record.workflow,
        "evaluation_mode": record.evaluation_mode,
        "document_gt_confirmed_at": timestamp(record.document_gt_confirmed_at) if record.document_gt_confirmed_at else None,
        "layout_confirmed_at": timestamp(record.layout_confirmed_at) if record.layout_confirmed_at else None,
        "layout_locked_at": timestamp(record.layout_locked_at) if record.layout_locked_at else None,
        "global_fields": [global_field_json(field) for field in record.global_fields],
        "ground_truth_raw": record.ground_truth_raw,
        "ground_truth_normalized": record.ground_truth_normalized,
        "status": record.status,
        "history_status": history_status(record),
        "created_at": timestamp(record.created_at),
        "updated_at": timestamp(record.updated_at),
        "categories": [category_json(category) for category in record.categories],
        "runs": [run_json(run, detail, summary=summary) for run in record.runs if not run.archived],
    }


def config_json(record, settings=None):
    from app.services.dynamic_pipeline_service import model_json
    keys = (
        "id",
        "pipeline_id",
        "name",
        "base_url",
        "endpoint",
        "http_method",
        "request_format",
        "file_field_name",
        "enabled",
        "engine",
        "include_roi",
        "query_params",
        "last_connection_status",
    )
    return {
        **{key: getattr(record, key) for key in keys},
        "execution_mode": record.execution_mode,
        "integrated_options": record.integrated_options,
        "source": record.source,
        "det_model_id": record.det_model_id,
        "rec_model_id": record.rec_model_id,
        "det_model": model_json(record.det_model),
        "rec_model": model_json(record.rec_model),
        "base_url": settings.model_gateway_base_url if settings else record.base_url,
        "api_key_configured": bool(settings.api_key(record.pipeline_id)) if settings else False,
        "created_at": timestamp(record.created_at),
        "updated_at": timestamp(record.updated_at),
    }
