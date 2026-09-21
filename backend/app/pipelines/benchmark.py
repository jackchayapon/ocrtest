"""Verified Gateway DET V6 -> ordered line crops -> baseline REC V5 (no model query)."""

import time
from uuid import uuid4

from app.integrations.model_gateway import GatewayError
from app.pipelines.base import CropInputAdapter
from app.pipelines.normalizers import MintResultNormalizer, average, bounded_text, number

DETECTION_ENDPOINT = "/api/v1/text-detection-batches"
RECOGNITION_ENDPOINT = "/api/v1/text-recognition-batches"


def invalid(message):
    return GatewayError(message, "INVALID_OCR_RESPONSE")


class BenchmarkPipelineAdapter(CropInputAdapter):
    engine = "det_v6_rec_v5"  # Internal display/config identifier; never sent as a query.
    detector = "PP-OCRv6_medium_det"
    recognition_batch_size = 8

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
        detection = await self.gateway.send(
            self.gateway.build_batch_request(
                pngs=[crop.png],
                endpoint=DETECTION_ENDPOINT,
                version=6,
                request_id=request_id + "_det",
            )
        )
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
        if not isinstance(polygons, list) or len(polygons) > 1000:
            raise invalid("Invalid or excessive detection regions")
        if scores is not None and (not isinstance(scores, list) or len(scores) != len(polygons)):
            raise invalid("Detection scores do not match regions")
        scores = scores or [None] * len(polygons)
        lines, recognition_batches = [], []
        with self.images.open(crop.png) as image:
            for start in range(0, len(polygons), self.recognition_batch_size):
                batch = polygons[start : start + self.recognition_batch_size]
                try:
                    pngs = [self.images.rectify_quad(image, polygon) for polygon in batch]
                except (ValueError, TypeError, OverflowError):
                    raise invalid("Detection returned an invalid quadrilateral") from None
                recognition = await self.gateway.send(
                    self.gateway.build_batch_request(
                        pngs=pngs,
                        endpoint=RECOGNITION_ENDPOINT,
                        version=5,
                        request_id=f"{request_id}_rec_{len(recognition_batches)}",
                    )
                )
                recognized = recognition["data"]
                items = recognized.get("results") if isinstance(recognized, dict) else None
                if (
                    not isinstance(items, list)
                    or len(items) != len(batch)
                    or recognized.get("count") != len(batch)
                ):
                    raise invalid("Recognition result count does not match line crops")
                for index, item in enumerate(items):
                    if not isinstance(item, dict):
                        raise invalid("Invalid recognition result")
                    lines.append(
                        dict(
                            polygon=batch[index],
                            det_score=scores[start + index],
                            text=bounded_text(item.get("text")),
                            rec_score=item.get("confidence"),
                        )
                    )
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
                "det_model": self.detector,
                "rec_model": self.recognizer,
            },
            "meta": meta,
            "detection": detection,
            "recognition_batches": recognition_batches,
            "composition": {
                "ordering": "detection_order",
                "line_count": len(lines),
                "recognition_endpoint": RECOGNITION_ENDPOINT,
                "recognition_version": "5",
            },
        }
        return self.normalize_result(
            payload, crop, roi, round((time.perf_counter() - started) * 1000)
        )
