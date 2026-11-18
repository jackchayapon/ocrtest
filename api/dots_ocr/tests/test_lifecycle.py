import io
import threading

from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from conftest import KEY, Reader, image_bytes


def test_shutdown_closes_reader_on_its_worker(settings):
    events = []

    class Managed(Reader):
        def __init__(self):
            events.append(("load", threading.get_ident()))

        def read(self, image):
            events.append(("read", threading.get_ident()))
            return super().read(image)

        def close(self):
            events.append(("close", threading.get_ident()))

    with TestClient(create_app(settings, lambda _: Managed())) as client:
        response = client.post(
            "/api/v1/ocr-text",
            headers={"Authorization": "Bearer " + KEY},
            files={"image": ("a", image_bytes())},
        )
        assert response.status_code == 200
    assert [e[0] for e in events] == ["load", "read", "close"]
    assert len({e[1] for e in events}) == 1


def test_exif_orientation_does_not_rotate_coordinates(client):
    with Image.new("RGB", (120, 80)) as image, io.BytesIO() as output:
        exif = image.getexif()
        exif[274] = 6
        image.save(output, "JPEG", exif=exif)
        result = client.post(
            "/api/v1/ocr-text", files={"image": ("a.jpg", output.getvalue())}
        )
    assert result.status_code == 200 and result.json()["data"]["image"] == {
        "width": 120,
        "height": 80,
    }


def test_animated_webp_rejected(client):
    with (
        Image.new("RGB", (100, 100), "white") as a,
        Image.new("RGB", (100, 100), "black") as b,
        io.BytesIO() as output,
    ):
        a.save(output, "WEBP", save_all=True, append_images=[b], duration=100, loop=0)
        result = client.post(
            "/api/v1/ocr-text", files={"image": ("a.webp", output.getvalue())}
        )
    assert (
        result.status_code == 415 and result.json()["error"]["code"] == "ANIMATED_IMAGE"
    )
