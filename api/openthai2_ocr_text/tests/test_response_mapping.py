import io
from copy import deepcopy

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.schemas import convert

HEADERS = {"X-API-Key": "synthetic-unit-test-key"}


def image_bytes(width=180, height=80, rotation=0):
    with Image.new("RGB", (width, height), "white") as original:
        image = original.rotate(rotation, expand=True)
        try:
            with io.BytesIO() as stream:
                image.save(stream, "PNG")
                return stream.getvalue(), image.size
        finally:
            image.close()


def model_result(rotation=0):
    return {"text": "ไทย English\nSecond row", "lines": [
        {"text": "ไทย", "row": np.int32(0), "confidence": np.float32(.95),
            "box": np.array([[50.5, 5.25], [75.5, 6.25], [74.5, 20.25], [49.5, 19.25]])},
        {"text": "English", "row": 0, "confidence": None,
            "box": [[5, 5], [35, 5], [35, 20], [5, 20]]},
        {"text": "Second row", "row": 1, "confidence": .9,
            "box": [[5, 35], [70, 35], [70, 50], [5, 50]]}],
        "rotation": rotation, "text_angle": -2.5}


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_single_batch_preserve_original_frame_and_full_model_text(rotation):
    raw = model_result(rotation)
    class Reader:
        def read(self, image):
            return deepcopy(raw)
    content, dimensions = image_bytes(rotation=rotation)
    with TestClient(create_app(Settings(_env_file=None), Reader), headers=HEADERS) as client:
        single = client.post("/api/v1/ocr-text", files={"image": ("synthetic.png", content, "image/png")})
        batch = client.post("/api/v1/ocr-text-batches", files=[("images", ("synthetic.png", content, "image/png"))]*2)
        assert single.status_code == batch.status_code == 200
        data = single.json()["data"]
        assert data["text"] == raw["text"]
        assert data["text"] != "\n".join(line["text"] for line in data["lines"])
        assert [line["row"] for line in data["lines"]] == [0, 0, 1]
        assert [line["text"] for line in data["lines"]] == [line["text"] for line in raw["lines"]]
        assert data["lines"][0]["box"] == raw["lines"][0]["box"].tolist()
        assert data["lines"][1]["confidence"] is None and data["confidence"] is None
        assert data["rotation"] == rotation and data["text_angle"] == -2.5
        assert data["image"] == {"width": dimensions[0], "height": dimensions[1]}
        items = batch.json()["data"]["results"]
        assert [item["index"] for item in items] == [0, 1]
        assert all(item["status"] == "success" and item["error"] is None and item["result"] == data for item in items)


def test_mixed_batch_indices_keep_errors_and_empty_results_separate():
    class Reader:
        def read(self, image):
            if image.width == 88:
                return {"text": "", "lines": []}
            return {"text": f"ไทย English {image.width}", "lines": []}
    first, _ = image_bytes(width=100)
    blank, _ = image_bytes(width=88)
    last, _ = image_bytes(width=120)
    with TestClient(create_app(Settings(_env_file=None), Reader), headers=HEADERS) as client:
        response = client.post("/api/v1/ocr-text-batches", files=[
            ("images", ("synthetic.png", value, "image/png")) for value in [first, b"corrupt", blank, last]])
        assert response.status_code == 200
        data = response.json()["data"]
        assert (data["total"], data["succeeded"], data["failed"]) == (4, 3, 1)
        items = data["results"]
        assert [item["index"] for item in items] == [0, 1, 2, 3]
        assert items[0]["result"]["text"] == "ไทย English 100"
        assert items[1]["status"] == "error" and items[1]["result"] is None
        assert items[1]["error"]["code"] == "INVALID_IMAGE"
        assert items[2]["status"] == "success" and items[2]["result"]["text"] == ""
        assert items[2]["result"]["lines"] == [] and items[2]["result"]["geometry_available"] is False
        assert items[3]["result"]["text"] == "ไทย English 120"
        assert "lines" not in data and "text" not in data


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "NaN", "Infinity"])
@pytest.mark.parametrize("field", ["box", "text_angle"])
def test_converter_rejects_nonfinite_values_after_numeric_coercion(field, value):
    raw = model_result()
    if field == "box":
        raw["lines"][1]["box"][0][0] = value
    else:
        raw[field] = value
    with pytest.raises(ValueError):
        convert(raw, 180, 80)


@pytest.mark.parametrize("field", ["box", "text_angle"])
@pytest.mark.parametrize("value", ["NaN", "Infinity"])
def test_invalid_native_numbers_keep_safe_http_and_batch_item_errors(field, value):
    class Reader:
        def read(self, image):
            raw = model_result()
            if image.width == 100:
                if field == "box":
                    raw["lines"][1]["box"][0][0] = value
                else:
                    raw[field] = value
            return raw
    invalid, _ = image_bytes(width=100)
    valid, _ = image_bytes(width=180)
    with TestClient(create_app(Settings(_env_file=None), Reader), headers=HEADERS) as client:
        single = client.post("/api/v1/ocr-text", files={"image": invalid})
        assert single.status_code == 500 and single.json()["error"]["code"] == "INTERNAL_ERROR"
        assert value not in single.text
        batch = client.post("/api/v1/ocr-text-batches", files=[("images", invalid), ("images", valid)])
        assert batch.status_code == 200
        data = batch.json()["data"]
        assert (data["total"], data["succeeded"], data["failed"]) == (2, 1, 1)
        assert data["results"][0]["status"] == "error" and data["results"][0]["result"] is None
        assert data["results"][0]["error"]["code"] == "MODEL_INFERENCE_FAILED"
        assert data["results"][1]["status"] == "success"
        assert data["results"][1]["result"]["text"] == model_result()["text"]
