import asyncio
import hashlib
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.batch import infer_one
from app.errors import ServiceError
from app.inference import Inference
from app.integrity import verify_snapshot
from app.main import create_app
from app.schemas import parse_output
from conftest import KEY, Reader, image_bytes


def test_concurrent_request_is_rejected_before_model(settings):
    entered, release = threading.Event(), threading.Event()
    calls = []

    class Controlled(Reader):
        def read(self, image):
            calls.append(1)
            entered.set()
            release.wait(3)
            return super().read(image)

    with TestClient(create_app(settings, lambda _: Controlled())) as client:
        client.headers["Authorization"] = "Bearer " + KEY
        responses = []
        thread = threading.Thread(
            target=lambda: responses.append(
                client.post("/api/v1/ocr-text", files={"image": ("a", image_bytes())})
            )
        )
        thread.start()
        try:
            assert entered.wait(2)
            second = client.post(
                "/api/v1/ocr-text", files={"image": ("a", image_bytes())}
            )
            assert second.status_code == 429 and calls == [1]
        finally:
            release.set()
            thread.join(3)
        assert responses[0].status_code == 200


def test_chunked_body_cannot_bypass_limit(client, settings):
    settings.max_upload_bytes = 1024
    result = client.post(
        "/api/v1/ocr-text",
        content=iter([b"x" * 40000, b"x" * 40000]),
        headers={"Content-Type": "multipart/form-data; boundary=test"},
    )
    assert result.status_code == 413


def test_batch_timeout_does_not_start_remaining_images(settings):
    calls = []

    class Slow(Reader):
        def read(self, image):
            calls.append(1)
            time.sleep(0.12)
            return super().read(image)

    settings.inference_timeout_seconds = 0.02
    with TestClient(create_app(settings, lambda _: Slow())) as client:
        response = client.post(
            "/api/v1/ocr-text-batches",
            headers={"Authorization": "Bearer " + KEY},
            files=[("images", ("a", image_bytes()))] * 4,
        )
        assert response.status_code == 504 and len(calls) == 1
        assert "data" not in response.json()


def test_batch_response_budget(client, settings):
    settings.max_batch_response_bytes = 700
    result = client.post(
        "/api/v1/ocr-text-batches", files=[("images", ("a", image_bytes()))] * 2
    )
    assert result.status_code == 502
    assert result.json()["error"]["code"] == "RESPONSE_TOO_LARGE"


def test_client_cancellation_keeps_pending_native_work(settings):
    entered, release = threading.Event(), threading.Event()

    class Controlled(Reader):
        def read(self, image):
            entered.set()
            release.wait(3)
            return super().read(image)

    async def scenario():
        inference = Inference(settings, lambda _: Controlled())
        inference.initialize()
        task = asyncio.create_task(infer_one(inference, image_bytes(), settings))
        while not entered.is_set():
            await asyncio.sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        try:
            with pytest.raises(ServiceError) as error:
                inference.submit(image_bytes())
            assert error.value.status == 429
        finally:
            release.set()
            await asyncio.shield(inference.pending)
            inference.executor.shutdown()

    asyncio.run(scenario())


def test_integrity_checks_contents_and_unexpected_code(tmp_path):
    path = tmp_path / "module.py"
    content = b"# pinned model code\n"
    path.write_bytes(content)
    digest = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
    entry = {
        "files": {
            "module.py": {
                "size": len(content),
                "algorithm": "git-blob-sha1",
                "hash": digest,
            }
        }
    }
    verify_snapshot(tmp_path, entry)
    path.write_bytes(content.replace(b"pinned", b"edited"))
    with pytest.raises(ValueError, match="integrity"):
        verify_snapshot(tmp_path, entry)
    path.write_bytes(content)
    (tmp_path / "untracked.py").write_text("# unexpected")
    with pytest.raises(ValueError, match="Unexpected"):
        verify_snapshot(tmp_path, entry)


def test_checkpoint_marker_cannot_hide_malformed_body():
    for raw in [
        "bad<|endofassistant|>",
        "[]<|endofassistant|>garbage",
        '[{"category":"Text","bbox":[0,0,1e308,1e308]}]',
    ]:
        with pytest.raises(ServiceError):
            parse_output(raw, (1000, 1000), (1, 1))


def test_json_no_fabricated_boxes_or_confidence():
    result = parse_output('[{"category":"Picture"}]', (100, 200), (112, 196))
    item = json.loads(result.model_dump_json())["elements"][0]
    assert item["bbox"] is None and item["native_bbox"] is None
    assert item["confidence"] is None and item["text"] is None
