import io
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.main import create_app

KEY = "synthetic-test-key-not-a-real-secret"


def image_bytes(value=1, format="PNG", size=(120, 80)):
    with Image.new("RGB", size, (value, 20, 30)) as image, io.BytesIO() as buffer:
        image.save(buffer, format=format)
        return buffer.getvalue()


class Reader:
    device, dtype = "test-double", "not-real-inference"

    def read(self, image):
        value = image.getpixel((0, 0))[0]
        return json.dumps(
            [
                {
                    "category": "Text",
                    "text": f"ภาพ image {value}",
                    "bbox": [10, 10, 40, 30],
                }
            ],
            ensure_ascii=False,
        ), image.size


@pytest.fixture
def settings():
    return Settings(_env_file=None, api_key=KEY)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, lambda _: Reader())) as client:
        client.headers["Authorization"] = "Bearer " + KEY
        yield client
