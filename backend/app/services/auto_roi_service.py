import math
from uuid import uuid4

from app.core.errors import AppError
from app.integrations.model_gateway import GatewayError, ModelGatewayClient
from app.pipelines.normalizers import confidence, number
from app.repositories.benchmark_repository import BenchmarkRepository
from app.services.test_case_service import TestCaseService


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
                    endpoint="/api/v1/document-layouts",
                    query_params={},
                    fields=data.model_dump(exclude={"page_number"}),
                    request_id=f"roi_{uuid4().hex}",
                )
            )
        except GatewayError as exc:
            raise AppError(
                f"Auto ROI is unavailable: {exc}. Draw a region manually to continue.", 503
            ) from None
        result = payload["data"]
        if not isinstance(result, dict):
            raise AppError(
                "Auto ROI returned an unsupported response. Manual selection remains available.",
                502,
            )
        suggestions = []
        regions = result.get("regions", result.get("text_lines", []))
        if not isinstance(regions, list):
            raise AppError(
                "Auto ROI returned invalid regions. Manual selection remains available.", 502
            )
        for region in regions[:1000]:
            if not isinstance(region, dict):
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
