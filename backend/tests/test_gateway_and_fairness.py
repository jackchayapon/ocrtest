import asyncio
import io
from email.parser import BytesParser
from email.policy import default
from hashlib import sha256

import httpx
import pytest
from PIL import Image

from app.db.models import PipelineConfig
from app.integrations.model_gateway import GatewayError, ModelGatewayClient
from app.pipelines.hutch_crop import HutchCropPipelineAdapter
from app.pipelines.hutch_full import HutchFullPipelineAdapter
from app.pipelines.mint import MintPipelineAdapter
from app.pipelines.normalizers import MintResultNormalizer, PaddleResultNormalizer
from app.services.image_service import ImageService


def envelope(engine):
    meta = {
        "request_id": "gateway-fixture-id",
        "duration_ms": 123.4,
        "service": "test-service",
        "model": "test-model",
    }
    if engine == "custom":
        return {
            "data": {
                "text": "ไทย",
                "confidence": 0.92,
                "lines": [
                    {
                        "polygon": [[2, 3], [50, 3], [50, 30], [2, 30]],
                        "text": "ไทย",
                        "det_score": 0.8,
                        "rec_score": 0.92,
                    }
                ],
            },
            "meta": meta,
        }
    return {
        "data": {
            "det_model": "PP-OCRv6_medium_det",
            "rec_model": "th_PP-OCRv5_mobile_rec",
            "predictions": [
                {
                    "res": {
                        "rec_texts": ["ไทย"],
                        "rec_scores": [0.9],
                        "rec_polys": [[[2, 3], [50, 3], [50, 30], [2, 30]]],
                    }
                }
            ],
        },
        "meta": meta,
    }


def multipart(request):
    message = BytesParser(policy=default).parsebytes(
        b"Content-Type: "
        + request.headers["content-type"].encode()
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + request.content
    )
    return {
        part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
        for part in message.iter_parts()
    }


def config(pipeline_id):
    return PipelineConfig(
        pipeline_id=pipeline_id,
        name=pipeline_id,
        enabled=True,
        base_url="https://gateway.example",
        endpoint="/api/v1/ocr-results",
        request_format="multipart",
        query_params={},
        engine="custom" if pipeline_id == "mint" else "paddle",
    )


def test_critical_crop_fairness_and_request_contract(settings, png, gateway, monkeypatch):
    behavior, calls = gateway
    behavior["handler"] = lambda request: httpx.Response(
        200, json=envelope(request.url.params["engine"])
    )
    images = ImageService(settings)
    original = images.open(png)
    roi = {"x1": 40, "y1": 30, "x2": 270, "y2": 150}
    shared = images.canonical_crop(original, roi)
    crop_invocations = []
    original_method = ImageService.canonical_crop

    def track_crop(self, image, region):
        crop_invocations.append(region)
        return original_method(self, image, region)

    monkeypatch.setattr(ImageService, "canonical_crop", track_crop)
    adapters = [
        MintPipelineAdapter(config("mint"), settings),
        HutchCropPipelineAdapter(config("hutch_crop"), settings),
        HutchFullPipelineAdapter(config("hutch_full"), settings),
    ]

    async def run():
        return await asyncio.gather(
            *(
                adapter.run(
                    original_image=original,
                    cropped_image=None if i == 2 else shared,
                    roi=roi,
                    request_id=f"benchmark-{i}",
                )
                for i, adapter in enumerate(adapters[:2])
            )
        )

    results = asyncio.run(run())
    assert crop_invocations == [], "Neither crop-input adapter repeats preprocessing"
    assert len(calls) == 2
    inputs = [multipart(request)["image"] for request in calls]
    assert inputs[0] == inputs[1] == shared.png
    assert all(Image.open(io.BytesIO(data)).size == (230, 120) for data in inputs)
    assert {sha256(data).hexdigest() for data in inputs} == {shared.sha256}
    assert {result.diagnostics["crop_sha256"] for result in results} == {shared.sha256}
    assert [result.diagnostics["crop_stage"] for result in results] == [
        "app_crop",
        "app_crop",
    ]
    for i, request in enumerate(calls):
        assert request.method == "POST"
        assert request.url.path == "/api/v1/ocr-results"
        assert request.headers["authorization"] == "Bearer test-gateway-secret"
        assert request.headers["x-request-id"] == f"benchmark-{i}"
        fields = multipart(request)
        assert "roi" not in fields
        if i:
            assert request.url.params["engine"] == "paddle"
            assert fields["text_det_unclip_ratio"] == b"1.7"
            assert fields["text_det_thresh"] == b"0.25"
            assert fields["text_det_box_thresh"] == b"0.6"
        else:
            assert request.url.params["engine"] == "custom"
    assert results[0].boxes[0]["bbox"] == [42.0, 33.0, 90.0, 60.0]
    assert results[0].boxes[0]["crop_bbox"] == [2.0, 3.0, 50.0, 30.0]
    assert results[0].diagnostics["gateway_duration_ms"] == 123.4
    assert results[0].diagnostics["gateway_request_id"] == "gateway-fixture-id"
    original.close()


def test_full_rejects_prebuilt_crop(settings, png):
    original = ImageService.open(png)
    crop = ImageService(settings).canonical_crop(original, None)
    with pytest.raises(GatewayError, match="never a pre-made crop"):
        asyncio.run(
            HutchFullPipelineAdapter(config("hutch_full"), settings).run(
                original_image=original, cropped_image=crop
            )
        )


def test_no_key_means_no_auth_header(settings, png):
    client = ModelGatewayClient(settings, api_key="")
    request = client.build_request(
        png=png, endpoint="/ocr", query_params={}, fields={}, request_id="id"
    )
    assert "Authorization" not in request["headers"]


@pytest.mark.parametrize(
    "failure,code",
    [
        ("timeout", "GATEWAY_TIMEOUT"),
        ("connect", "GATEWAY_UNAVAILABLE"),
        ("http", "AUTHENTICATION_REQUIRED"),
        ("malformed", "INVALID_RESPONSE"),
    ],
)
def test_gateway_failures_are_safe(settings, png, gateway, failure, code):
    behavior, calls = gateway

    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("test-gateway-secret", request=request)
        if failure == "connect":
            raise httpx.ConnectError("test-gateway-secret", request=request)
        if failure == "malformed":
            return httpx.Response(200, json={"bad": "test-gateway-secret"})
        return httpx.Response(
            401,
            json={
                "error": {
                    "code": "AUTHENTICATION_REQUIRED",
                    "message": "test-gateway-secret",
                    "request_id": "upstream-id",
                }
            },
        )

    behavior["handler"] = handler
    gateway_client = ModelGatewayClient(settings)
    with pytest.raises(GatewayError) as error:
        asyncio.run(
            gateway_client.send(
                gateway_client.build_request(
                    png=png, endpoint="/ocr", query_params={}, fields={}, request_id="our-id"
                )
            )
        )
    assert error.value.code == code
    assert "test-gateway-secret" not in str(error.value)
    assert len(calls) == 1, "No retries of deterministic HTTP failures"


def test_normalizers_keep_missing_confidence_null():
    mint = MintResultNormalizer().normalize({"text": "plain"}, crop_size=(100, 100))
    paddle = PaddleResultNormalizer().normalize(
        {"predictions": [{"rec_texts": ["plain"]}]}, crop_size=(100, 100)
    )
    assert mint.confidence is None and paddle.confidence is None
    assert not mint.boxes and not paddle.boxes
    assert (
        PaddleResultNormalizer().normalize({"predictions": []}, crop_size=(100, 100)).final_text
        == ""
    )


def test_json_base64_contract(settings, png):
    request = ModelGatewayClient(settings).build_request(
        png=png,
        endpoint="/ocr",
        query_params={},
        fields={"text_det_unclip_ratio": 1.7},
        request_id="id",
        request_format="json_base64",
    )
    assert request["json"]["image"].startswith("data:image/png;base64,")
    assert request["json"]["text_det_unclip_ratio"] == 1.7
