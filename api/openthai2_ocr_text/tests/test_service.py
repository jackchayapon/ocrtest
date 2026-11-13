import io
import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.schemas import convert

TEST_HEADERS = {"X-API-Key": "synthetic-unit-test-key"}


class Reader:
    def read(self, image):
        return {"text": "", "lines": [], "rotation": 0, "text_angle": 0}


@pytest.fixture
def png():
    with Image.new("RGB", (300, 220), "white") as image, io.BytesIO() as stream:
        image.save(stream, "PNG")
        return stream.getvalue()


@pytest.fixture
def client():
    with TestClient(create_app(Settings(_env_file=None), Reader), headers=TEST_HEADERS) as value:
        yield value


def test_blank_http_contract(client, png):
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/readiness").json()["status"] == "ready"
    response = client.post("/api/v1/ocr-text", files={"image": ("x.png", png)})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data == {"text": "", "lines": [], "confidence": None, "geometry_available": False,
                    "image": {"width": 300, "height": 220}, "rotation": 0, "text_angle": 0}
    assert response.headers["x-request-id"] == response.json()["meta"]["request_id"]


@pytest.mark.parametrize("mode", ["bearer", "x-api-key"])
def test_authentication(mode, png):
    with TestClient(create_app(Settings(_env_file=None, api_key="synthetic-private-key"), Reader)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/readiness").status_code == 401
        assert client.post("/api/v1/ocr-text", headers={"Authorization": "Bearer wrong"}, content=png).status_code == 401
        headers = {"Authorization": "Bearer synthetic-private-key"} if mode == "bearer" else {"X-API-Key": "synthetic-private-key"}
        assert client.post("/api/v1/ocr-text", files={"image": png}, headers=headers).status_code == 200


@pytest.mark.parametrize("key", ["", "   ", "invalid\nkey"])
def test_missing_or_misconfigured_key_fails_closed(key, png):
    loaded = []
    def loader():
        loaded.append(True)
        return Reader()
    with TestClient(create_app(Settings(_env_file=None, api_key=key), loader)) as client:
        assert client.get("/health").json() == {"status": "alive"}
        for path in ["/api/v1/readiness", "/api/v1/ocr-text", "/api/v1/ocr-text-batches"]:
            response = client.get(path) if path.endswith("readiness") else client.post(path, files={"image": png})
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"
            assert response.headers["x-request-id"] == response.json()["error"]["request_id"]
        assert loaded == []


def test_unset_api_key_keeps_only_liveness_available(monkeypatch):
    monkeypatch.delenv("OPENTHAI_API_KEY", raising=False)
    with TestClient(create_app(Settings(_env_file=None), Reader)) as client:
        assert client.get("/health").json() == {"status": "alive"}
        assert client.get("/api/v1/readiness").status_code == 503
        assert client.app.state.inference.reader is None


def test_not_ready():
    def fail():
        raise RuntimeError("private/model/path")
    with TestClient(create_app(Settings(_env_file=None), fail), headers=TEST_HEADERS) as client:
        assert client.get("/health").status_code == 200
        for path in ("/api/v1/readiness", "/api/v1/ocr-text"):
            response = client.get(path) if path.endswith("readiness") else client.post(path)
            assert response.status_code == 503
            assert "private/model/path" not in response.text


@pytest.mark.parametrize("content,code", [(b"", "IMAGE_REQUIRED"), (b"not an image", "INVALID_IMAGE")])
def test_invalid_image(client, content, code):
    response = client.post("/api/v1/ocr-text", files={"image": ("claimed.png", content, "image/png")})
    assert response.status_code == 422 and response.json()["error"]["code"] == code


def test_input_limits_and_formats(png):
    with TestClient(create_app(Settings(_env_file=None, max_pixels=10), Reader), headers=TEST_HEADERS) as client:
        assert client.post("/api/v1/ocr-text", files={"image": png}).status_code == 413
    with TestClient(create_app(Settings(_env_file=None, max_upload_bytes=10), Reader), headers=TEST_HEADERS) as client:
        assert client.post("/api/v1/ocr-text", files={"image": png}).status_code == 413
        assert client.post("/api/v1/ocr-text", content=b"x" * 70000).status_code == 413
    with Image.new("RGB", (20, 20)) as image, io.BytesIO() as output:
        image.save(output, "GIF")
        with TestClient(create_app(Settings(_env_file=None), Reader), headers=TEST_HEADERS) as client:
            assert client.post("/api/v1/ocr-text", files={"image": ("fake.png", output.getvalue())}).status_code == 415
            assert client.post("/api/v1/ocr-text", json={}).status_code == 415
            assert client.post("/api/v1/ocr-text", files={"wrong": png}).status_code == 422


def test_numpy_order_and_polygons():
    result = convert({"text": "ไทย\nEnglish", "lines": [
        {"text": "ไทย", "row": np.int32(0), "confidence": np.float32(.9),
         "box": np.array([[1, 2], [20, 2], [20, 10], [1, 10]])},
        {"text": "English", "row": 1, "confidence": None,
         "box": [[2, 12], [30, 12], [30, 20], [2, 20]]}]}, 100, 40)
    assert result["text"] == "ไทย\nEnglish"
    assert result["lines"][0]["row"] == 0
    assert result["lines"][0]["confidence"] == pytest.approx(.9)
    assert result["confidence"] is None


def test_concurrent_admission_and_failure_cleanup(png):
    started, release = threading.Event(), threading.Event()
    class SlowReader:
        def read(self, image):
            started.set()
            release.wait(5)
            raise RuntimeError("private document text")
    with TestClient(create_app(Settings(_env_file=None), SlowReader), headers=TEST_HEADERS) as client:
        results = []
        thread = threading.Thread(target=lambda: results.append(client.post("/api/v1/ocr-text", files={"image": png})))
        thread.start()
        assert started.wait(5)
        busy = client.post("/api/v1/ocr-text", files={"image": png})
        assert busy.status_code == 429 and busy.headers["retry-after"] == "5"
        assert client.get("/health").status_code == 200
        release.set()
        thread.join(5)
        assert results[0].status_code == 500
        assert "private document" not in results[0].text
        client.app.state.inference.reader = Reader()
        assert client.post("/api/v1/ocr-text", files={"image": png}).status_code == 200


def test_deadline_keeps_native_slot_until_completion(png):
    class SlowReader(Reader):
        def read(self, image):
            time.sleep(.2)
            return super().read(image)
    with TestClient(create_app(Settings(_env_file=None, request_timeout_seconds=.05), SlowReader), headers=TEST_HEADERS) as client:
        response = client.post("/api/v1/ocr-text", files={"image": png})
        assert response.status_code == 504
        assert client.post("/api/v1/ocr-text", files={"image": png}).status_code == 429
        time.sleep(.25)
        client.app.state.inference.reader = Reader()
        assert client.post("/api/v1/ocr-text", files={"image": png}).status_code == 200


def test_jpeg_and_output_limit(png):
    with Image.open(io.BytesIO(png)) as image, io.BytesIO() as stream:
        image.save(stream, "JPEG")
        jpeg = stream.getvalue()
    class LargeReader(Reader):
        def read(self, image):
            return {"text": "ก" * 1024, "lines": []}
    with TestClient(create_app(Settings(_env_file=None, max_response_bytes=1024), LargeReader), headers=TEST_HEADERS) as client:
        result = client.post("/api/v1/ocr-text", files={"image": ("misleading.png", jpeg, "image/png")})
        assert result.status_code == 503 and result.json()["error"]["code"] == "OUTPUT_TOO_LARGE"


def test_chunked_body_limit_and_bad_multipart():
    with TestClient(create_app(Settings(_env_file=None, max_upload_bytes=32), Reader), headers=TEST_HEADERS) as client:
        response = client.post("/api/v1/ocr-text", content=iter([b"x" * 40000, b"y" * 40000]),
                               headers={"Content-Type": "multipart/form-data; boundary=abc"})
        assert response.status_code in {400, 413}
        # Invalid preamble can be rejected before consuming the remaining body.
        assert "error" in response.json()
        malformed = client.post("/api/v1/ocr-text", content=b"broken", headers={"Content-Type": "multipart/form-data"})
        assert malformed.status_code == 400 and malformed.json()["error"]["code"] == "BAD_REQUEST"


def test_model_output_caps_and_corrupt_snapshot(tmp_path):
    with pytest.raises(ValueError):
        convert({"text": "", "lines": [{}] * 1025}, 10, 10)
    with pytest.raises(ValueError):
        convert({"text": "x" * 32769, "lines": []}, 10, 10)
    with TestClient(create_app(Settings(_env_file=None, model_dir=tmp_path)), headers=TEST_HEADERS) as client:
        assert client.get("/api/v1/readiness").status_code == 503
