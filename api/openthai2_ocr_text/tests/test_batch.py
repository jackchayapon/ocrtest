import asyncio
import io
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from starlette.datastructures import UploadFile

from app.config import Settings
from app.main import create_app
from app.schemas import BatchEnvelope

PATH = "/api/v1/ocr-text-batches"


def png(width=30):
    with Image.new("RGB", (width, 20), "white") as image, io.BytesIO() as stream:
        image.save(stream, "PNG")
        return stream.getvalue()


class Reader:
    def read(self, image):
        return {"text": f"ภาพ {image.width}", "lines": [], "rotation": 0, "text_angle": 0}


def files(values):
    return [("images", (f"synthetic-{index}.png", value, "image/png")) for index, value in enumerate(values)]


@pytest.mark.parametrize("count", [1, 2, 4, 8])
def test_batch_order_counts_single_model_and_single_compatibility(count):
    loaded = []
    def loader():
        loaded.append(True)
        return Reader()
    with TestClient(create_app(Settings(_env_file=None), loader)) as client:
        response = client.post(PATH, files=files([png(30+index) for index in range(count)]))
        assert response.status_code == 200, response.text
        value = BatchEnvelope.model_validate(response.json())
        assert value.data.total == value.data.succeeded == count and value.data.failed == 0
        assert [item.index for item in value.data.results] == list(range(count))
        assert [item.result.text for item in value.data.results] == [f"ภาพ {30+index}" for index in range(count)]
        assert all(item.result.confidence is None and not item.result.geometry_available and item.error is None for item in value.data.results)
        assert response.headers["x-request-id"] == value.meta["request_id"]
        single = client.post("/api/v1/ocr-text", files={"image": png()})
        assert single.status_code == 200 and single.json()["data"] == response.json()["data"]["results"][0]["result"]
        assert loaded == [True]


def test_mixed_corrupt_empty_and_native_failure_are_per_image_and_redacted(caplog):
    caplog.set_level("INFO", logger="openthai")
    class FaultReader(Reader):
        def read(self, image):
            if image.width == 31:
                raise RuntimeError("private OCR text and private-provider-key")
            return super().read(image)
    with TestClient(create_app(Settings(_env_file=None), FaultReader)) as client:
        response = client.post(PATH, files=files([png(), b"corrupt", b"", png(31), png(32)]))
        assert response.status_code == 200
        payload = response.json()["data"]
        assert (payload["total"], payload["succeeded"], payload["failed"]) == (5, 2, 3)
        assert [item["status"] for item in payload["results"]] == ["success", "error", "error", "error", "success"]
        assert [item["error"]["code"] for item in payload["results"][1:4]] == ["INVALID_IMAGE", "IMAGE_REQUIRED", "MODEL_INFERENCE_FAILED"]
        assert "private OCR" not in response.text + caplog.text
        assert "private-provider-key" not in response.text + caplog.text
        assert "batch_image request_id=" in caplog.text


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"X-API-Key": "wrong"}])
def test_batch_authentication_required(headers):
    with TestClient(create_app(Settings(_env_file=None, api_key="synthetic-batch-key"), Reader)) as client:
        response = client.post(PATH, headers=headers, files=files([png()]))
        assert response.status_code == 401 and response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("headers", [{"Authorization": "Bearer synthetic-batch-key"}, {"X-API-Key": "synthetic-batch-key"}])
def test_batch_authentication_supported(headers):
    with TestClient(create_app(Settings(_env_file=None, api_key="synthetic-batch-key"), Reader)) as client:
        assert client.post(PATH, headers=headers, files=files([png()])).status_code == 200


def test_structure_limits_and_no_inference_for_rejected_batch():
    called = []
    class TrackingReader(Reader):
        def read(self, image):
            called.append(True)
            return super().read(image)
    with TestClient(create_app(Settings(_env_file=None, max_batch_images=2), TrackingReader)) as client:
        excessive = client.post(PATH, files=files([png()] * 3))
        assert excessive.status_code == 413 and excessive.json()["error"]["code"] == "TOO_MANY_IMAGES"
        excessive = client.post(PATH, files=files([png()] * 4))
        assert excessive.status_code == 413 and excessive.json()["error"]["code"] == "TOO_MANY_IMAGES"
        empty = client.post(PATH, content=b"--empty--\r\n", headers={"Content-Type": "multipart/form-data; boundary=empty"})
        assert empty.status_code == 422 and empty.json()["error"]["code"] == "IMAGES_REQUIRED"
        assert client.post(PATH, json={"images": []}).status_code == 415
        assert client.post(PATH, files={"image": png()}).status_code == 422
        malformed = client.post(PATH, content=b"broken", headers={"Content-Type": "multipart/form-data"})
        assert malformed.status_code == 400 and malformed.json()["error"]["code"] == "BAD_REQUEST"
        assert called == []


def test_upload_pixel_per_image_and_aggregate_response_limits():
    with TestClient(create_app(Settings(_env_file=None, max_batch_upload_bytes=10), Reader)) as client:
        response = client.post(PATH, files=files([png()]))
        assert response.status_code == 413
    with TestClient(create_app(Settings(_env_file=None, max_upload_bytes=10), Reader)) as client:
        response = client.post(PATH, files=files([png()]))
        assert response.status_code == 200
        assert response.json()["data"]["results"][0]["error"]["code"] == "PAYLOAD_TOO_LARGE"
    with TestClient(create_app(Settings(_env_file=None, max_pixels=10), Reader)) as client:
        response = client.post(PATH, files=files([png()]))
        assert response.json()["data"]["results"][0]["error"]["code"] == "IMAGE_TOO_LARGE"
    class LargeReader(Reader):
        def read(self, image):
            return {"text": "ก" * 300, "lines": []}
    with TestClient(create_app(Settings(_env_file=None, max_batch_response_bytes=1024), LargeReader)) as client:
        response = client.post(PATH, files=files([png(), png()]))
        assert response.status_code == 503 and response.json()["error"]["code"] == "OUTPUT_TOO_LARGE"


@pytest.mark.parametrize("first", ["single", "batch"])
def test_single_and_batch_share_busy_admission(first):
    started, release = threading.Event(), threading.Event()
    class SlowReader(Reader):
        def read(self, image):
            started.set()
            release.wait(5)
            return super().read(image)
    with TestClient(create_app(Settings(_env_file=None), SlowReader)) as client, ThreadPoolExecutor(1) as executor:
        def run():
            return client.post(PATH, files=files([png()])) if first == "batch" else client.post("/api/v1/ocr-text", files={"image": png()})
        future = executor.submit(run)
        assert started.wait(5)
        for path, uploads in [(PATH, files([png()])), ("/api/v1/ocr-text", {"image": png()})]:
            busy = client.post(path, files=uploads)
            assert busy.status_code == 429 and busy.headers["retry-after"] == "5"
        release.set()
        assert future.result(5).status_code == 200


def test_batch_timeout_retains_slot_and_stops_remaining_images():
    calls = []
    class SlowReader(Reader):
        def read(self, image):
            calls.append(image.width)
            time.sleep(.2)
            return super().read(image)
    with TestClient(create_app(Settings(_env_file=None, batch_timeout_seconds=.05), SlowReader)) as client:
        response = client.post(PATH, files=files([png(), png(31)]))
        assert response.status_code == 504
        assert client.post("/api/v1/ocr-text", files={"image": png()}).status_code == 429
        time.sleep(.25)
        assert calls == [30]
        client.app.state.inference.reader = Reader()
        assert client.post(PATH, files=files([png()])).status_code == 200


def test_upload_and_decoded_resources_are_closed(monkeypatch):
    closed = []
    decoded = []
    class TrackingReader(Reader):
        def read(self, image):
            decoded.append(image)
            return super().read(image)
    original = UploadFile.close
    async def close(upload):
        await original(upload)
        closed.append(upload.file.closed)
    monkeypatch.setattr(UploadFile, "close", close)
    with TestClient(create_app(Settings(_env_file=None), TrackingReader)) as client:
        assert client.post(PATH, files=files([png(), b"corrupt", png(31)])).status_code == 200
        assert len(closed) == 3 and all(closed)
        assert client.app.state.inference.pending.done()
        assert len(decoded) == 2
        for image in decoded:
            with pytest.raises(ValueError):
                image.getpixel((0, 0))


def test_disconnect_stops_batch_and_preserves_native_slot():
    async def scenario():
        started = threading.Event()
        release = threading.Event()
        calls = []
        class SlowReader(Reader):
            def read(self, image):
                calls.append(image.width)
                started.set()
                release.wait(3)
                return super().read(image)
        app = create_app(Settings(_env_file=None), SlowReader)
        body = b""
        boundary = b"synthetic"
        for index in range(2):
            body += b'--'+boundary+b'\r\nContent-Disposition: form-data; name="images"; filename="image.png"\r\nContent-Type: image/png\r\n\r\n'+png(30+index)+b'\r\n'
        body += b'--'+boundary+b'--\r\n'
        messages = []
        delivered = False
        async def receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type":"http.request", "body":body, "more_body":False}
            await asyncio.to_thread(started.wait, 2)
            return {"type":"http.disconnect"}
        async def send(message):
            messages.append(message)
        scope = {"type":"http", "asgi":{"version":"3.0"}, "http_version":"1.1", "method":"POST", "scheme":"http",
            "path":PATH,"raw_path":PATH.encode(),"query_string":b"", "root_path":"", "server":("test",80),"client":("test",1),
            "headers":[(b"content-type",b"multipart/form-data; boundary="+boundary),(b"content-length",str(len(body)).encode())]}
        async with app.router.lifespan_context(app):
            try:
                await app(scope, receive, send)
                assert calls == [30] and not app.state.inference.pending.done()
                assert next(message["status"] for message in messages if message["type"]=="http.response.start")==499
            finally:
                release.set()
                await asyncio.shield(app.state.inference.pending)
    asyncio.run(scenario())


def test_batch_can_be_disabled_and_bounds_cannot_be_bypassed():
    with pytest.raises(ValueError):
        Settings(_env_file=None, max_batch_images=17)
    with pytest.raises(ValueError):
        Settings(_env_file=None, max_concurrent_batch_requests=2)
    with TestClient(create_app(Settings(_env_file=None, max_concurrent_batch_requests=0), Reader)) as client:
        response = client.post(PATH, files=files([png()]))
        assert response.status_code == 503 and response.json()["error"]["code"] == "BATCH_DISABLED"
        assert client.post("/api/v1/ocr-text", files={"image":png()}).status_code == 200


def test_batch_jpeg_and_per_image_output_limit():
    with Image.new("RGB", (40, 20), "white") as image, io.BytesIO() as stream:
        image.save(stream, "JPEG")
        jpeg = stream.getvalue()
    class LargeReader(Reader):
        def read(self, image):
            if image.width == 30:
                return {"text": "ก" * 2000, "lines": []}
            return super().read(image)
    with TestClient(create_app(Settings(_env_file=None, max_response_bytes=1024), LargeReader)) as client:
        response = client.post(PATH, files=files([png(), jpeg]))
        assert response.status_code == 200
        results = response.json()["data"]["results"]
        assert results[0]["error"]["code"] == "OUTPUT_TOO_LARGE"
        assert results[1]["result"]["image"] == {"width": 40, "height": 20}


def test_chunked_batch_body_is_bounded_before_inference():
    with TestClient(create_app(Settings(_env_file=None, max_batch_upload_bytes=32), Reader)) as client:
        body = iter([b'--bound\r\nContent-Disposition: form-data; name="images"; filename="x.png"\r\n\r\n', b"x" * 70000, b"\r\n--bound--\r\n"])
        response = client.post(PATH, content=body, headers={"Content-Type":"multipart/form-data; boundary=bound"})
        assert response.status_code == 413 and response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_batch_model_not_ready_and_openapi_contract():
    def fail():
        raise RuntimeError("private model path")
    with TestClient(create_app(Settings(_env_file=None), fail)) as client:
        response = client.post(PATH, files=files([png()]))
        assert response.status_code == 503 and response.json()["error"]["code"] == "MODEL_NOT_READY"
        assert "private model path" not in response.text
        schema = client.get("/openapi.json").json()["paths"][PATH]["post"]
        assert schema["requestBody"]["content"]["multipart/form-data"]["schema"]["required"] == ["images"]


@pytest.mark.parametrize("failure", ["disconnect", "body_limit", "timeout"])
def test_interrupted_multipart_upload_closes_partial_files(monkeypatch, failure):
    import starlette.formparsers
    handles = []
    original = starlette.formparsers.SpooledTemporaryFile
    def tracked_file(*args, **kwargs):
        handle = original(*args, **kwargs)
        handles.append(handle)
        return handle
    monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", tracked_file)

    async def scenario():
        app = create_app(Settings(_env_file=None, max_batch_upload_bytes=32, batch_timeout_seconds=.05), Reader)
        delivered = False
        messages = []
        async def receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b'--bound\r\nContent-Disposition: form-data; name="images"; filename="x.png"\r\n\r\npartial', "more_body": True}
            if failure == "disconnect":
                return {"type": "http.disconnect"}
            if failure == "body_limit":
                return {"type": "http.request", "body": b"x" * 70000, "more_body": False}
            await asyncio.sleep(1)
            raise AssertionError("The upload deadline should cancel receive")
        async def send(message):
            messages.append(message)
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
            "path": PATH, "raw_path": PATH.encode(), "query_string": b"", "root_path": "", "server": ("test", 80), "client": ("test", 1),
            "headers": [(b"content-type", b"multipart/form-data; boundary=bound")]}
        async with app.router.lifespan_context(app):
            await app(scope, receive, send)
            assert len(handles) == 1 and handles[0].closed
            assert app.state.inference.pending is None
            status = next(message["status"] for message in messages if message["type"] == "http.response.start")
            assert status == {"disconnect": 499, "body_limit": 413, "timeout": 504}[failure]
    asyncio.run(scenario())
