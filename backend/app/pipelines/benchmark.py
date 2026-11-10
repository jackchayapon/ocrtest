"""Verified Gateway DET V6 -> ordered line crops -> baseline REC V5 (no model query)."""

import time
from uuid import uuid4

from app.core.batching import IMAGE_BATCH_SIZE
from app.core.config import MAX_DETECTION_REGIONS, MAX_OCR_TEXT_CHARACTERS
from app.integrations.model_gateway import GatewayError
from app.pipelines.base import CropInputAdapter
from app.pipelines.normalizers import (
    MintResultNormalizer,
    average,
    bounded_text,
    number,
    recognition_items,
)

DETECTION_ENDPOINT = "/api/v1/text-detection-batches"
RECOGNITION_ENDPOINT = "/api/v1/text-recognition-batches"


def invalid(message):
    return GatewayError(message, "INVALID_OCR_RESPONSE")


class BenchmarkPipelineAdapter(CropInputAdapter):
    detection_endpoint = DETECTION_ENDPOINT
    recognition_endpoint = RECOGNITION_ENDPOINT
    detection_version = 6
    engine = "det_v6_rec_v5"  # Internal display/config identifier; never sent as a query.
    detector = "PP-OCRv6_medium_det"
    recognition_batch_size = IMAGE_BATCH_SIZE
    recognition_version = 5
    model_variant = None

    def line_batches(self, polygons):
        """Retain order, bound small-line groups to 1 MP; one large line at a time."""
        batch, pixels = [], 0
        for polygon in polygons:
            try:
                width, height = self.images.rectified_size(polygon)
            except (ValueError, TypeError, OverflowError):
                raise invalid("Detection returned an invalid quadrilateral") from None
            if batch and (pixels + width * height > 1_000_000 or len(batch) >= self.recognition_batch_size):
                yield batch
                batch, pixels = [], 0
            batch.append(polygon)
            pixels += width * height
        if batch:
            yield batch

    def batch_request(self, **kwargs):
        request = self.gateway.build_batch_request(**kwargs)
        if self.model_variant is not None:
            request["params"]["model"] = self.model_variant
        return request

    def selected_model(self, response, fallback):
        # Baseline Benchmark retains its established model configuration.
        if self.model_variant is None:
            return fallback
        data = response.get("data", {})
        selection = data.get("model_selection", {}) if isinstance(data, dict) else {}
        name = selection.get("model_name") if isinstance(selection, dict) else None
        return name[:255] if isinstance(name, str) and name else fallback

    def parse_response(self, data, *, offset, crop_size):
        return MintResultNormalizer().normalize(data, offset=offset, crop_size=crop_size)

    async def run(self, *, original_image=None, cropped_image=None, roi=None, request_id=None):
        started = time.perf_counter()
        request_id = request_id or f"ocr_{uuid4().hex}"
        self.diagnostics = dict(
            request_id=request_id,
            roi=roi,
            crop_stage=self.crop_stage,
            original_width=original_image.width if original_image else None,
            original_height=original_image.height if original_image else None,
            detector_model=self.detector,
            recognizer_model=self.recognizer,
        )
        self.failure_stage = "input_crop"
        crop = self.prepare_input(original_image, cropped_image, roi)
        self.diagnostics.update(
            input_width=crop.width,
            input_height=crop.height,
            input_sha256=crop.sha256,
            crop_width=crop.width,
            crop_height=crop.height,
            crop_sha256=crop.sha256,
            input_byte_size=len(crop.png),
            input_format="image/png",
        )
        if not self.config.enabled:
            raise GatewayError("Pipeline is disabled", "PIPELINE_DISABLED")
        self.failure_stage = "detection_request"
        detection = await self.gateway.send(
            self.batch_request(
                pngs=[crop.png],
                endpoint=self.detection_endpoint,
                version=self.detection_version,
                request_id=request_id + "_det",
            )
        )
        self.failure_stage = "detection_contract"
        self.diagnostics["gateway_request_id"] = detection.get("meta", {}).get("request_id")
        data = detection["data"]
        if (
            not isinstance(data, dict)
            or data.get("kind") != "text_detection_batch"
            or data.get("contract_version") != "leaf-inference-v1"
        ):
            raise invalid("Unexpected detection batch contract")
        results = (
            data.get("result", {}).get("results") if isinstance(data.get("result"), dict) else None
        )
        if (
            not isinstance(results, list)
            or len(results) != 1
            or not isinstance(results[0], dict)
            or data.get("count") != 1
        ):
            raise invalid("Detection result count does not match the input batch")
        polygons = results[0].get("dt_polys")
        scores = results[0].get("dt_scores")
        if not isinstance(polygons, list) or len(polygons) > MAX_DETECTION_REGIONS:
            raise invalid(f"Detection exceeds supported {MAX_DETECTION_REGIONS} regions per Field")
        if scores is not None and (not isinstance(scores, list) or len(scores) != len(polygons)):
            raise invalid("Detection scores do not match regions")
        scores = scores or [None] * len(polygons)
        lines, recognition_batches = [], []
        text_size = 0
        start = 0
        for batch in self.line_batches(polygons):
            self.failure_stage = "crop_rectification"
            # CPU-only pixel scope: do not keep a decoded full page alive while
            # awaiting REC and admitting the next adapter. Routes/order stay unchanged.
            with crop.pixels(self.images) as image:
                try:
                    pngs = [self.images.rectify_quad(image, polygon) for polygon in batch]
                except (ValueError, TypeError, OverflowError):
                    raise invalid("Detection returned an invalid quadrilateral") from None
            self.failure_stage = "recognition_request"
            recognition = await self.gateway.send(
                self.batch_request(
                    pngs=pngs,
                    endpoint=self.recognition_endpoint,
                    version=self.recognition_version,
                    request_id=f"{request_id}_rec_{len(recognition_batches)}",
                )
            )
            self.failure_stage = "recognition_contract"
            self.diagnostics["gateway_request_id"] = recognition.get("meta", {}).get("request_id")
            for index, item in enumerate(recognition_items(recognition["data"], len(batch))):
                text_size += len(item["text"]) + bool(lines)
                if text_size > MAX_OCR_TEXT_CHARACTERS:
                    raise invalid("Gateway returned invalid or excessive OCR text")
                lines.append(dict(polygon=batch[index], det_score=scores[start + index], **item))
            start += len(batch)
            recognition_batches.append(recognition)
        text = bounded_text("\n".join(line["text"] for line in lines))
        responses = [detection, *recognition_batches]
        durations = [number(response["meta"].get("duration_ms")) for response in responses]
        meta = dict(detection["meta"])
        meta["duration_ms"] = (
            sum(durations) if all(d is not None and d >= 0 for d in durations) else None
        )
        # Top-level tracing references DET; complete per-stage metadata stays in raw_response.
        payload = {
            "data": {
                "text": text,
                "lines": lines,
                "confidence": average(line["rec_score"] for line in lines),
                "det_model": self.selected_model(detection, self.detector),
                "rec_model": self.selected_model(recognition_batches[0], self.recognizer)
                if recognition_batches else self.recognizer,
            },
            "meta": meta,
            "detection": detection,
            "recognition_batches": recognition_batches,
            "composition": {
                "ordering": "detection_order",
                "line_count": len(lines),
                "recognition_endpoint": self.recognition_endpoint,
                "recognition_version": str(self.recognition_version),
            },
        }
        if self.model_variant is not None:
            payload["composition"].update(detection_version="6", model=self.model_variant)
        self.failure_stage = "normalization"
        return self.normalize_result(
            payload, crop, roi, round((time.perf_counter() - started) * 1000)
        )
