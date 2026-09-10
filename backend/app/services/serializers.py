from datetime import timezone


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


def run_json(record):
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
    data = {key: getattr(record, key) for key in fields}
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
    }


def test_case_json(record):
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
        "ground_truth_raw": record.ground_truth_raw,
        "ground_truth_normalized": record.ground_truth_normalized,
        "status": record.status,
        "created_at": timestamp(record.created_at),
        "updated_at": timestamp(record.updated_at),
        "categories": [category_json(category) for category in record.categories],
        "runs": [run_json(run) for run in record.runs if not run.archived],
    }


def config_json(record, settings=None):
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
        "api_key_configured": bool(settings.api_key(record.pipeline_id)) if settings else False,
        "created_at": timestamp(record.created_at),
        "updated_at": timestamp(record.updated_at),
    }
