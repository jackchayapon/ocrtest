import math
import re
from uuid import uuid4

from app.core.errors import AppError
from app.integrations.model_gateway import GatewayError, ModelGatewayClient
from app.pipelines.normalizers import confidence, number
from app.repositories.benchmark_repository import BenchmarkRepository
from app.services.test_case_service import TestCaseService

TEXT_REGION_TYPES = {
    "text", "text_line", "text_block", "paragraph", "paragraph_title", "title",
    "heading", "header", "footer", "caption", "figure_caption", "table_caption",
    "document_title", "section_header", "page_header", "page_footer", "page_number",
    "list", "list_item", "reference", "reference_content", "footnote", "abstract",
}
NON_TEXT_REGION_TYPES = {"image", "picture", "figure", "photo", "photograph", "illustration", "logo", "chart", "table", "seal", "stamp", "formula"}


def is_text_region(region, *, text_only=False):
    """Explicit layout classes take precedence over a text detector's default mode.

    Older text-line responses contain only bbox/score; retain that contract, but
    never infer a text class from numeric class IDs or unknown layout classes.
    """
    labels = []
    for key in ("label", "type", "category", "class_name", "region_type", "block_label"):
        value = region.get(key)
        if value is not None and value != "":
            if not isinstance(value, str):
                return False
            labels.append(re.sub(r"[\s-]+", "_", value.strip().lower()))
    if labels:
        return not any(label in NON_TEXT_REGION_TYPES for label in labels) and all(label in TEXT_REGION_TYPES for label in labels)
    if "class_id" in region:
        return False
    return text_only or any(isinstance(region.get(key), str) and region[key].strip() for key in ("text", "rec_text"))


def layout_prediction_response(data):
    """Adapt the verified single-image layout model body to existing ROI parsing."""
    if isinstance(data, dict):
        return data
    message = "Auto ROI returned an unsupported response. Manual selection remains available."
    if (not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict)
            or not isinstance(data[0].get("boxes"), list)):
        raise AppError(message, 502)
    regions = []
    for box in data[0]["boxes"][:1000]:
        if not isinstance(box, dict):
            raise AppError(message, 502)
        coordinates = box.get("coordinate")
        label = box.get("label")
        if (not isinstance(coordinates, list) or len(coordinates) != 4
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not math.isfinite(value) for value in coordinates)
                or coordinates[0] >= coordinates[2] or coordinates[1] >= coordinates[3]
                or not isinstance(label, str) or not label.strip()):
            raise AppError(message, 502)
        regions.append({"bbox": coordinates, "label": label, "score": box.get("score"),
                        "source": "layout-predictions"})
    return {"regions": regions}


class AutoROIService:
    def __init__(self, session, settings, storage):
        self.repository = BenchmarkRepository(session)
        self.gateway = ModelGatewayClient(settings)
        self.storage = storage
        self.cases = TestCaseService(session, settings, storage)

    async def suggest(self, document_id, data):
        document = self.repository.document(document_id)
        png, width, height = self.cases.page_image(document, data.page_number)
        try:
            payload = await self.gateway.send(
                self.gateway.build_request(
                    png=png,
                    endpoint="/api/v1/layout-predictions",
                    query_params={},
                    fields=data.model_dump(exclude={"page_number"}),
                    request_id=f"roi_{uuid4().hex}",
                )
            )
        except GatewayError as exc:
            raise AppError(
                f"Auto ROI is unavailable: {exc}. Draw a region manually to continue.", 503
            ) from None
        result = layout_prediction_response(payload["data"])
        suggestions = []
        regions = result.get("regions", result.get("text_lines", []))
        if not isinstance(regions, list):
            raise AppError(
                "Auto ROI returned invalid regions. Manual selection remains available.", 502
            )
        for region in regions[:1000]:
            if not isinstance(region, dict):
                continue
            if not is_text_region(region, text_only=data.auto_roi_mode == "text-line" or "regions" not in result):
                continue
            bbox = region.get("bbox")
            if isinstance(bbox, dict):
                values = [number(bbox.get(k)) for k in ("x", "y", "width", "height")]
                if all(value is not None for value in values):
                    x, y, w, h = values
                    bbox = [x, y, x + w, y + h]
            if not bbox and isinstance(region.get("bbox_ratio"), list):
                ratios = region["bbox_ratio"]
                if len(ratios) == 4 and all(number(v) is not None for v in ratios):
                    bbox = [
                        float(v) * (width if i % 2 == 0 else height) for i, v in enumerate(ratios)
                    ]
            if (
                not isinstance(bbox, (list, tuple))
                or len(bbox) != 4
                or any(number(v) is None for v in bbox)
            ):
                continue
            x1, y1 = math.floor(float(bbox[0])), math.floor(float(bbox[1]))
            x2, y2 = math.ceil(float(bbox[2])), math.ceil(float(bbox[3]))
            x1, x2 = max(0, x1), min(width, x2)
            y1, y2 = max(0, y1), min(height, y2)
            if x1 < x2 and y1 < y2:
                suggestions.append(
                    {
                        "id": str(len(suggestions)),
                        "roi": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                        "score": confidence(region.get("score")),
                        "source": str(region.get("source", "gateway"))[:100],
                    }
                )
        return {
            "regions": suggestions,
            "request_id": payload["meta"].get("request_id"),
        }
