"""Normalize reference Gateway data here, never in the frontend or manager."""

import math
from dataclasses import dataclass, field

from app.integrations.model_gateway import GatewayError


def number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def confidence(value):
    score = number(value)
    return score if score is not None and 0 <= score <= 1 else None


def average(values):
    scores = [score for value in values if (score := confidence(value)) is not None]
    return sum(scores) / len(scores) if scores else None


@dataclass
class NormalizedOCR:
    raw_text: str
    final_text: str
    confidence: float | None
    boxes: list[dict] = field(default_factory=list)
    detector: str | None = None
    recognizer: str | None = None


def geometry(line, offset, crop_size):
    polygon = line.get("polygon")
    bbox = line.get("bbox")
    if polygon is None and isinstance(bbox, list) and len(bbox) >= 3 and isinstance(bbox[0], list):
        polygon = bbox
    if isinstance(polygon, list) and len(polygon) >= 3:
        if not all(
            isinstance(p, (list, tuple)) and len(p) == 2 and all(number(v) is not None for v in p)
            for p in polygon
        ):
            return None
        polygon = [
            [max(0, min(crop_size[0], float(x))), max(0, min(crop_size[1], float(y)))]
            for x, y in polygon
        ]
        bbox = [
            min(p[0] for p in polygon),
            min(p[1] for p in polygon),
            max(p[0] for p in polygon),
            max(p[1] for p in polygon),
        ]
    else:
        polygon = None
        if (
            not isinstance(bbox, (list, tuple))
            or len(bbox) != 4
            or any(number(v) is None for v in bbox)
        ):
            return None
        bbox = [max(0, min(crop_size[i % 2], float(v))) for i, v in enumerate(bbox)]
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    rec = confidence(line.get("rec_score", line.get("rec_confidence", line.get("confidence"))))
    return {
        "bbox": [v + offset[i % 2] for i, v in enumerate(bbox)],
        "crop_bbox": bbox,
        "polygon": [[x + offset[0], y + offset[1]] for x, y in polygon] if polygon else None,
        "crop_polygon": polygon,
        "text": str(line.get("text") or ""),
        "confidence": rec,
        "rec_confidence": rec,
        "det_confidence": confidence(line.get("det_score", line.get("det_confidence"))),
    }


def bounded_text(value):
    if not isinstance(value, str) or len(value) > 100000:
        raise GatewayError("Gateway returned invalid or excessive OCR text", "INVALID_OCR_RESPONSE")
    return value


class MintResultNormalizer:
    def normalize(self, data, *, offset=(0, 0), crop_size):
        if not isinstance(data, dict):
            raise GatewayError("Mint response data is not an object", "INVALID_OCR_RESPONSE")
        lines = next(
            (
                data[key]
                for key in ("lines", "segments", "predictions")
                if isinstance(data.get(key), list) and data[key]
            ),
            [],
        )
        lines = [line for line in lines if isinstance(line, dict)]
        if "text" not in data and "final_text" not in data and not lines:
            raise GatewayError(
                "Mint response has no recognized text fields", "INVALID_OCR_RESPONSE"
            )
        text = data.get("text", "\n".join(str(line.get("text") or "") for line in lines))
        final = bounded_text(data.get("final_text", text))
        raw = bounded_text(data.get("raw_text", text))
        boxes = [box for line in lines if (box := geometry(line, offset, crop_size)) is not None]
        score = confidence(data.get("confidence"))
        return NormalizedOCR(
            raw,
            final,
            score
            if score is not None
            else average(line.get("rec_score", line.get("confidence")) for line in lines),
            boxes,
            data.get("det_model"),
            data.get("rec_model"),
        )


class PaddleResultNormalizer:
    def normalize(self, data, *, offset=(0, 0), crop_size):
        if not isinstance(data, (dict, list)):
            raise GatewayError(
                "Paddle response data is not an object or list", "INVALID_OCR_RESPONSE"
            )
        predictions = data.get("predictions", [data]) if isinstance(data, dict) else data
        if isinstance(predictions, dict):
            predictions = [predictions]
        if not isinstance(predictions, list):
            raise GatewayError("Paddle predictions are invalid", "INVALID_OCR_RESPONSE")
        texts, scores, boxes = [], [], []
        recognized_shape = not predictions
        for prediction in predictions:
            if not isinstance(prediction, dict):
                continue
            while isinstance(prediction.get("res"), dict):
                prediction = prediction["res"]
            if "rec_texts" in prediction:
                recognized_shape = True
                rec_texts = prediction["rec_texts"]
                if not isinstance(rec_texts, list):
                    raise GatewayError("Paddle text list is invalid", "INVALID_OCR_RESPONSE")
                rec_scores = prediction.get("rec_scores") or []
                polygons = prediction.get("rec_polys") or prediction.get("dt_polys") or []
                bboxes = prediction.get("rec_boxes") or []
                det_scores = prediction.get("dt_scores") or []
                for i, text in enumerate(rec_texts):
                    texts.append(bounded_text(text))
                    rec = rec_scores[i] if i < len(rec_scores) else None
                    scores.append(rec)
                    line = {
                        "text": text,
                        "rec_score": rec,
                        "det_score": det_scores[i] if i < len(det_scores) else None,
                        "polygon": polygons[i] if i < len(polygons) else None,
                        "bbox": bboxes[i] if i < len(bboxes) else None,
                    }
                    if (box := geometry(line, offset, crop_size)) is not None:
                        boxes.append(box)
            elif "rec_text" in prediction or "text" in prediction:
                recognized_shape = True
                text = bounded_text(prediction.get("rec_text", prediction.get("text")))
                texts.append(text)
                scores.append(prediction.get("rec_score", prediction.get("confidence")))
                if (box := geometry({**prediction, "text": text}, offset, crop_size)) is not None:
                    boxes.append(box)
        meta = data if isinstance(data, dict) else {}
        if not recognized_shape and "text" not in meta and "final_text" not in meta:
            raise GatewayError(
                "Unsupported Paddle prediction shape; capture a sanitized fixture to extend the normalizer",
                "UNSUPPORTED_PADDLE_RESPONSE",
            )
        text = meta.get("text", "\n".join(texts))
        score = confidence(meta.get("confidence"))
        return NormalizedOCR(
            bounded_text(meta.get("raw_text", text)),
            bounded_text(meta.get("final_text", text)),
            score if score is not None else average(scores),
            boxes,
            meta.get("det_model"),
            meta.get("rec_model"),
        )
