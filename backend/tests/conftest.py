import io

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.integrations.model_gateway import ModelGatewayClient
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        storage_path=tmp_path / "uploads",
        model_gateway_base_url="https://gateway.example",
        model_gateway_api_key="test-gateway-secret",
    )


@pytest.fixture
def gateway(monkeypatch):
    calls = []
    from tests.upstream_fixture import response
    behavior = {"handler": response}

    def handler(request):
        calls.append(request)
        return behavior["handler"](request)

    monkeypatch.setattr(
        ModelGatewayClient,
        "_client",
        lambda self, timeout=None: httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=timeout or 1
        ),
    )
    return behavior, calls


@pytest.fixture
def client(settings, gateway):
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def png():
    image = Image.new("RGB", (300, 200), "white")
    for x in range(40, 260):
        for y in range(50, 90):
            image.putpixel((x, y), (x % 255, y % 255, (x + y) % 255))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def document(client, png):
    response = client.post("/api/documents", files={"file": ("fixture.png", png, "image/png")})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def case(client, document):
    response = client.post(
        "/api/test-cases",
        json={
            "document_id": document["id"],
            "roi": {"x1": 40, "y1": 30, "x2": 270, "y2": 150},
            "ground_truth_raw": "บริษัท ซีดีจี จำกัด",
            "category_codes": ["thai_text", "stamp"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
