import io
import json
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr

from app.errors import ServiceError
from app.main import create_app
from app.schemas import parse_output
from conftest import KEY, Reader, image_bytes


@pytest.mark.parametrize("count", [1, 2, 4, 8])
def test_batch_order_identity_and_single_equivalence(client, count):
    batch = client.post(
        "/api/v1/ocr-text-batches",
        files=[("images", ("untrusted.png", image_bytes(i))) for i in range(count)],
    )
    assert batch.status_code == 200
    data = batch.json()["data"]
    assert data["count"] == data["succeeded"] == count
    assert data["failed"] == 0
    assert data["execution"] == "sequential_wrapper"
    for i, item in enumerate(data["results"]):
        assert (
            item["index"] == i and item["status"] == "success" and item["error"] is None
        )
        single = client.post(
            "/api/v1/ocr-text", files={"image": ("same.png", image_bytes(i))}
        )
        assert item["result"] == single.json()["data"]
        assert item["result"]["text"] == f"ภาพ image {i}"
        assert item["result"]["elements"][0]["confidence"] is None


def test_mixed_batch_and_safe_error(client):
    response = client.post(
        "/api/v1/ocr-text-batches",
        files=[
            ("images", ("a", image_bytes())),
            ("images", ("private-filename", b"bad image")),
            ("images", ("c", image_bytes(2))),
        ],
    )
    data = response.json()["data"]
    assert (
        response.status_code == 200 and data["succeeded"] == 2 and data["failed"] == 1
    )
    assert [i["index"] for i in data["results"]] == [0, 1, 2]
    assert data["results"][1]["result"] is None
    assert data["results"][1]["error"]["code"] == "INVALID_IMAGE"
    assert "private-filename" not in response.text


@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP"])
def test_decodable_image_types(client, format):
    result = client.post(
        "/api/v1/ocr-text", files={"image": ("image", image_bytes(format=format))}
    )
    assert result.status_code == 200
    assert result.json()["data"]["image"] == {"width": 120, "height": 80}


@pytest.mark.parametrize(
    "payload,code", [(b"", "IMAGE_REQUIRED"), (b"broken", "INVALID_IMAGE")]
)
def test_invalid_bytes(client, payload, code):
    result = client.post("/api/v1/ocr-text", files={"image": ("a", payload)})
    assert result.status_code == 422 and result.json()["error"]["code"] == code


def test_pdf_rejected_without_inference(client):
    with Image.new("RGB", (100, 100)) as image, io.BytesIO() as buffer:
        image.save(buffer, "PDF")
        result = client.post(
            "/api/v1/ocr-text",
            files={"image": ("a.pdf", buffer.getvalue(), "application/pdf")},
        )
    assert result.status_code == 415  # No PDF rendering is attempted.


def test_gif_rejected(client):
    response = client.post(
        "/api/v1/ocr-text", files={"image": ("a.gif", image_bytes(format="GIF"))}
    )
    assert response.status_code == 415


def test_pixel_rejection_before_model(client, settings):
    settings.max_pixels = 3136
    response = client.post("/api/v1/ocr-text", files={"image": ("a", image_bytes())})
    assert (
        response.status_code == 413
        and response.json()["error"]["code"] == "IMAGE_TOO_LARGE"
    )


def test_file_byte_limit(client, settings):
    settings.max_upload_bytes = 1024
    response = client.post("/api/v1/ocr-text", files={"image": ("a", b"x" * 1025)})
    assert response.status_code == 413


@pytest.mark.parametrize(
    "files",
    [[("wrong", ("a", b"x"))], [("image", ("a", b"x")), ("image", ("b", b"x"))]],
)
def test_wrong_or_duplicate_fields(client, files):
    assert client.post("/api/v1/ocr-text", files=files).status_code in {400, 422}


def test_batch_too_many_and_empty(client):
    assert (
        client.post(
            "/api/v1/ocr-text-batches", files=[("images", ("a", b"x"))] * 9
        ).status_code
        == 400
    )
    assert client.post("/api/v1/ocr-text-batches", content=b"{}").status_code == 415


@pytest.mark.parametrize("header", [None, "Bearer wrong", "X-API-Key fake"])
def test_auth_before_parsing(client, header):
    client.headers.pop("Authorization")
    response = client.post(
        "/api/v1/ocr-text",
        content=b"not multipart",
        headers={"Authorization": header} if header else {},
    )
    assert response.status_code == 401
    assert response.headers["x-request-id"] == response.json()["meta"]["request_id"]


def test_fail_closed_and_public_health(settings):
    settings.api_key = SecretStr("")
    with TestClient(create_app(settings, lambda _: Reader())) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/readiness").status_code == 503
        assert (
            client.post("/api/v1/ocr-text").json()["error"]["code"]
            == "AUTH_NOT_CONFIGURED"
        )


def test_readiness_load_failure(settings):
    def fail(_):
        raise RuntimeError("sensitive error details")

    with TestClient(create_app(settings, fail)) as client:
        client.headers["Authorization"] = "Bearer " + KEY
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/readiness").status_code == 503
        response = client.post(
            "/api/v1/ocr-text", files={"image": ("a", image_bytes())}
        )
        assert response.status_code == 503 and "sensitive" not in response.text


def test_logs_never_include_credentials_text_or_filenames(client, caplog):
    with caplog.at_level("INFO", logger="dots.requests"):
        client.post(
            "/api/v1/ocr-text", files={"image": ("private-name", image_bytes())}
        )
        client.get("/unknown-private-path?secret=hidden")
    assert "status=200" in caplog.text and "request_id=" in caplog.text
    for forbidden in [
        KEY,
        "private-name",
        "ภาพ image",
        "unknown-private-path",
        "hidden",
    ]:
        assert forbidden not in "\n".join(
            r.message for r in caplog.records if r.name == "dots.requests"
        )


@pytest.mark.parametrize(
    "failure,status,code",
    [
        (RuntimeError("private"), 502, "MODEL_INFERENCE_FAILED"),
        (MemoryError(), 503, "RESOURCE_EXHAUSTED"),
        (ServiceError("OUTPUT_TRUNCATED", "Truncated", 502), 502, "OUTPUT_TRUNCATED"),
    ],
)
def test_native_errors_are_safe(settings, failure, status, code):
    class Broken(Reader):
        def read(self, image):
            raise failure

    with TestClient(create_app(settings, lambda _: Broken())) as client:
        result = client.post(
            "/api/v1/ocr-text",
            headers={"Authorization": "Bearer " + KEY},
            files={"image": ("a", image_bytes())},
        )
    assert result.status_code == status and result.json()["error"]["code"] == code
    assert "private" not in result.text


def test_timeout_keeps_native_slot_until_worker_finishes(settings):
    started, finish = threading.Event(), threading.Event()

    class Slow(Reader):
        def read(self, image):
            started.set()
            finish.wait(3)
            return super().read(image)

    settings.inference_timeout_seconds = 0.05
    with TestClient(create_app(settings, lambda _: Slow())) as client:
        client.headers["Authorization"] = "Bearer " + KEY
        try:
            first = client.post(
                "/api/v1/ocr-text", files={"image": ("a", image_bytes())}
            )
            assert started.is_set() and first.status_code == 504
            second = client.post(
                "/api/v1/ocr-text", files={"image": ("a", image_bytes())}
            )
            assert second.status_code == 429 and second.headers["retry-after"] == "5"
        finally:
            finish.set()
        for _ in range(100):
            if client.app.state.inference.pending.done():
                break
            time.sleep(0.01)
        assert (
            client.post(
                "/api/v1/ocr-text", files={"image": ("a", image_bytes())}
            ).status_code
            == 200
        )


def test_http_request_timeout_also_retains_native_slot(settings):
    settings.request_timeout_seconds = 0.02

    class Slow(Reader):
        def read(self, image):
            time.sleep(0.15)
            return super().read(image)

    with TestClient(create_app(settings, lambda _: Slow())) as client:
        client.headers["Authorization"] = "Bearer " + KEY
        assert (
            client.post(
                "/api/v1/ocr-text", files={"image": ("a", image_bytes())}
            ).status_code
            == 504
        )
        assert (
            client.post(
                "/api/v1/ocr-text", files={"image": ("a", image_bytes())}
            ).status_code
            == 429
        )


def test_response_limit(client, settings):
    settings.max_response_bytes = 10
    result = client.post("/api/v1/ocr-text", files={"image": ("a", image_bytes())})
    assert (
        result.status_code == 502
        and result.json()["error"]["code"] == "RESPONSE_TOO_LARGE"
    )


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        "null",
        "garbage",
        '[{"category":"Text","bbox":[0,0,NaN,4]}]',
        '[{"category":"Text","bbox":[0,0,1]}]',
        '[{"category":"Text","bbox":[0,0,true,2]}]',
        '[{"category":"Text","bbox":[2,2,1,1]}]',
        '[{"category":"Text","text":2}]',
        '[{"text":"no category"}]',
        '[{"category":"Text"}] trailing',
    ],
)
def test_malformed_native_output_rejected(raw):
    with pytest.raises(ServiceError, match="valid layout JSON"):
        parse_output(raw, (100, 100), (100, 100))


def test_scaled_boxes_reading_order_table_formula_and_native_preserved():
    native = [
        {"category": "Text", "bbox": [50, 30, 90, 50], "text": "ภาษาไทย English"},
        {
            "category": "Table",
            "bbox": [10, 5, 20, 10],
            "text": "<table><tr><td>A</td></tr></table>",
        },
        {"category": "Formula", "text": r"x^2+1"},
        {"category": "Picture"},
    ]
    raw = json.dumps(native, ensure_ascii=False) + "<|endofassistant|>"
    result = parse_output(raw, (200, 300), (100, 100))
    assert result.native_output == raw and result.elements[0].native_bbox == [
        50,
        30,
        90,
        50,
    ]
    assert result.elements[0].bbox == [100, 90, 180, 150]
    assert result.tables == [1] and result.elements[3].text is None
    assert [e.index for e in result.elements] == [0, 1, 2, 3]
    assert result.text == "ภาษาไทย English\n<table><tr><td>A</td></tr></table>\nx^2+1"
    assert result.image.width == 200 and result.model_image.width == 100


@pytest.mark.parametrize("raw", ["[]", "```json\n[]\n```", "[]<|endofassistant|>"])
def test_empty_native_result(raw):
    result = parse_output(raw, (10, 20), (28, 56))
    assert result.text == "" and result.elements == [] and result.native_output == raw


def test_observed_blank_out_of_frame_box_is_not_published_as_valid_geometry():
    raw = '[{"category":"Picture","bbox":[0,0,1036,1034]}]'
    result = parse_output(raw, (800, 220), (812, 224))
    element = result.elements[0]
    assert element.native_bbox == [0, 0, 1036, 1034]
    assert element.bbox is None and element.geometry_status == "out_of_bounds"
    assert result.native_output == raw and result.text == ""


def test_real_loopback_http_contract(settings):
    """Real TCP/HTTP with a test double: explicitly NOT real-model validation."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings, lambda _: Reader()),
            host="127.0.0.1",
            port=port,
            log_level="critical",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if server.started:
                break
            time.sleep(0.01)
        assert server.started
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}",
            trust_env=False,
            headers={"Authorization": "Bearer " + KEY},
        ) as client:
            assert client.get("/api/v1/readiness").status_code == 200
            result = client.post(
                "/api/v1/ocr-text", files={"image": ("a.png", image_bytes())}
            )
            assert (
                result.status_code == 200
                and result.json()["data"]["text"] == "ภาพ image 1"
            )
    finally:
        server.should_exit = True
        thread.join(5)
    assert not thread.is_alive()
