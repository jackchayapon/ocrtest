import asyncio
import json

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from app.core.errors import AppError
from app.core.external_quota import SharedQuota
from app.db.models import ExternalProvider, PipelineConfig
from app.integrations.external_ocr import ExternalClient, get_provider
from app.integrations.model_gateway import GatewayError
from app.main import create_app
from app.services.ocr_jobs import snapshot
from app.services.provider_credentials import decrypt_credential
from tests import test_external_ocr

KEY = "synthetic-write-only-provider-key"

external = test_external_ocr.external


@pytest.fixture
def encryption(settings):
    settings.external_ocr_encryption_keys = SecretStr(Fernet.generate_key().decode())


def definition(**changes):
    return {"name": "Shared OCR", "endpoint": "https://public-ocr.example/v1/text",
            "auth_mode": "bearer", "credential_action": "replace", "api_key": KEY, **changes}


def create(client, **changes):
    response = client.post("/api/external-providers", json=definition(**changes))
    assert response.status_code == 201, response.text
    assert KEY not in response.text
    return response.json()


def test_anonymous_crud_persists_across_restart_and_secrets_are_write_only(client, settings, encryption):
    provider = create(client)
    assert provider["managed"] and provider["api_key_configured"]
    with client.app.state.database.session_factory() as session:
        record = session.get(ExternalProvider, provider["id"])
        encrypted = record.encrypted_credential
        assert KEY not in encrypted and KEY not in json.dumps(record.config)
        assert decrypt_credential(settings, encrypted, record.id, record.config["endpoint"]) == KEY
    # New application and DB sessions, not an in-memory registry masquerading as persistence.
    with TestClient(create_app(settings)) as restarted:
        response = restarted.get("/api/external-providers/" + provider["id"])
        assert response.json()["api_key_configured"] and KEY not in response.text
        response = restarted.put("/api/external-providers/" + provider["id"], json=definition(
            name="Renamed", api_key=None, credential_action="keep", enabled=False))
        assert response.status_code == 200 and not response.json()["enabled"]
        assert restarted.get("/api/pipelines/external-providers").json() == []
        assert restarted.delete("/api/external-providers/" + provider["id"]).status_code == 204
        assert restarted.get("/api/external-providers/" + provider["id"]).status_code == 404


def test_origin_change_requires_new_key_and_same_origin_keeps_key(client, settings, encryption):
    provider = create(client)
    path = "/api/external-providers/" + provider["id"]
    for changes in [dict(credential_action="keep", api_key=None), dict(api_key=KEY)]:
        response = client.put(path, json=definition(endpoint="https://other.example/ocr", **changes))
        assert response.status_code == 422 and KEY not in response.text
    assert client.get(path).json()["endpoint"] == provider["endpoint"]
    assert client.put(path, json=definition(endpoint="https://public-ocr.example/other",
        credential_action="keep", api_key=None)).status_code == 200
    assert client.put(path, json=definition(endpoint="https://other.example/ocr", api_key="synthetic-new-origin-key")).status_code == 200
    with client.app.state.database.session_factory() as session:
        record = session.get(ExternalProvider, provider["id"])
        assert decrypt_credential(settings, record.encrypted_credential, record.id, record.config["endpoint"]) == "synthetic-new-origin-key"
        for other_id, other_endpoint in [(record.id, provider["endpoint"]), ("another-provider", record.config["endpoint"])]:
            with pytest.raises(AppError):
                decrypt_credential(settings, record.encrypted_credential, other_id, other_endpoint)
    cleared = client.put(path, json=definition(endpoint="https://third.example/ocr", auth_mode="none", credential_action="remove", api_key=None))
    assert cleared.status_code == 200 and not cleared.json()["api_key_configured"]


def test_rotation_missing_wrong_keys_fail_closed_and_key_ring_works(client, settings, encryption):
    provider = create(client)
    old = settings.external_ocr_encryption_keys.get_secret_value()
    settings.external_ocr_encryption_keys = SecretStr(Fernet.generate_key().decode() + "," + old)
    assert get_provider(settings, provider["id"]).secret() == KEY
    settings.external_ocr_encryption_keys = SecretStr(Fernet.generate_key().decode())
    assert client.get("/api/external-providers").json()[0]["api_key_configured"]
    with pytest.raises(GatewayError) as error:
        get_provider(settings, provider["id"]).secret()
    assert error.value.code == "EXTERNAL_CREDENTIAL_UNAVAILABLE"
    settings.external_ocr_encryption_keys = SecretStr("")
    response = client.post("/api/external-providers", json=definition())
    assert response.status_code == 503 and KEY not in response.text


@pytest.mark.parametrize("endpoint", ["http://public.example/ocr", "https://127.0.0.1/ocr",
    "https://169.254.169.254/latest/meta-data", "https://10.0.0.1/ocr", "https://[::1]/ocr",
    "https://user:password@public.example/ocr", "https://public.example/ocr?key=hidden"])
def test_public_crud_does_not_remove_ssrf_boundary(client, encryption, endpoint):
    response = client.post("/api/external-providers", json=definition(endpoint=endpoint))
    assert response.status_code == 422 and KEY not in response.text


@pytest.mark.parametrize("changes", [dict(credential_env="EXTERNAL_OCR_SECRET_TEST"),
    dict(api_key="secret\r\nInjected: header"), dict(api_key="contains space"), dict(auth_header="Authorization"),
    dict(readiness_url="https://other.example/health"), dict(text_path="__import__('os')"),
    dict(auth_mode="none"), dict(credential_action="keep"), dict(extra="unrecognized")])
def test_rejects_credential_references_header_injection_and_unsafe_contract(client, encryption, changes):
    response = client.post("/api/external-providers", json=definition(**changes))
    assert response.status_code == 422 and KEY not in response.text


def test_atomic_pipeline_binding_snapshots_and_secret_free_http(client, settings, encryption, external):
    response = client.post("/api/external-pipelines", json={"pipeline_name": "Public external", "provider": definition()})
    assert response.status_code == 200, response.text
    pipeline = response.json()
    provider_id = pipeline["external_provider"]["provider_id"]
    with client.app.state.database.session_factory() as session:
        stored = session.scalar(select(PipelineConfig).where(PipelineConfig.pipeline_id == pipeline["pipeline_id"]))
        frozen = snapshot(stored)
        assert KEY not in json.dumps(frozen) and "encrypted_credential" not in json.dumps(frozen)
    assert client.delete("/api/external-providers/" + provider_id).status_code == 409
    changed = client.put("/api/external-providers/" + provider_id, json=definition(name="Updated", endpoint="https://public-ocr.example/new"))
    assert changed.status_code == 200
    with client.app.state.database.session_factory() as session:
        stored = session.scalar(select(PipelineConfig).where(PipelineConfig.pipeline_id == pipeline["pipeline_id"]))
        assert frozen["integrated_options"] != stored.integrated_options
    _, calls = external
    asyncio.run(ExternalClient(settings, get_provider(settings, provider_id)).request("test", b"synthetic-png"))
    assert calls[-1].headers["Authorization"] == "Bearer " + KEY
    assert calls[-1].url.path == "/new"
    for path in ["/api/external-providers", "/api/pipelines", "/api/health"]:
        text = client.get(path).text
        assert KEY not in text and "encrypted_credential" not in text


def test_server_provider_cannot_be_overwritten_or_credential_transferred(client, settings, encryption, external):
    response = client.put("/api/external-providers/openthai", json=definition())
    assert response.status_code == 404
    response = client.post("/api/external-pipelines", json={"pipeline_name": "Unsafe transfer", "provider_id": "openthai",
        "provider": definition(credential_action="keep", api_key=None)})
    assert response.status_code == 422
    response = client.post("/api/external-providers", json=definition(credential_action="keep", api_key=None))
    assert response.status_code == 422
    assert get_provider(settings, "openthai").secret() == "synthetic-provider-secret"


def test_failed_pipeline_does_not_leave_provider_or_secret(client, encryption):
    response = client.post("/api/external-pipelines", json={"pipeline_name": "Missing pipeline", "pipeline_id": "dynamic_" + "0" * 32, "provider": definition()})
    assert response.status_code == 404
    assert client.get("/api/external-providers").json() == []


def test_shared_limits_body_capacity_and_window_reset(client, settings, encryption):
    clock = [1.0]
    settings._external_shared_quota = SharedQuota(lambda: clock[0])
    for _ in range(30):
        assert client.post("/api/external-providers/validate", json=definition()).status_code == 200
    response = client.post("/api/external-providers/validate", json=definition())
    assert response.status_code == 429 and int(response.headers["Retry-After"]) > 0
    clock[0] += 61
    response = client.post("/api/external-providers", content=b"x" * 65537, headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_external_concurrency_bound_and_cancellation_release(settings, encryption, monkeypatch):
    from app.integrations.external_ocr import Provider
    provider = Provider(name="Bounded", endpoint="https://public.example/ocr")
    async def scenario():
        entered = asyncio.Event()
        unblock = asyncio.Event()
        async def request(self, *args):
            entered.set()
            await unblock.wait()
            return {"ok": True}
        monkeypatch.setattr(ExternalClient, "_request", request)
        tasks = [asyncio.create_task(ExternalClient(settings, provider).request("test", b"png")) for _ in range(2)]
        await entered.wait()
        with pytest.raises(GatewayError) as error:
            await ExternalClient(settings, provider).request("blocked", b"png")
        assert error.value.http_status == 429
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        unblock.set()
        assert await ExternalClient(settings, provider).request("released", b"png") == {"ok": True}
    asyncio.run(scenario())


@pytest.mark.parametrize("field", ["name", "endpoint", "image_field"])
def test_credentials_cannot_be_saved_in_public_fields(client, encryption, field):
    value = "https://public.example/" + KEY if field == "endpoint" else KEY.replace("-", "_") if field == "image_field" else KEY
    response = client.post("/api/external-providers", json=definition(**{field: value, "api_key": value if field != "endpoint" else KEY}))
    assert response.status_code == 422
    assert KEY not in response.text
    assert client.get("/api/external-providers").json() == []


@pytest.mark.parametrize("payload", [b'{"items":[' + b'0,' * 60000 + b'0]}', b'{"nested":' + b'[' * 40 + b'0' + b']' * 40 + b'}'], ids=["too_many_nodes", "too_deep"])
def test_external_structure_bounded_before_object_graph(settings, external, payload, monkeypatch):
    external[0]["handler"] = lambda request: httpx.Response(200, content=payload)
    parsed = []
    original = json.loads
    def loads(value, *args, **kwargs):
        if value == payload:
            parsed.append(True)
        return original(value, *args, **kwargs)
    monkeypatch.setattr(json, "loads", loads)
    with pytest.raises(GatewayError) as error:
        asyncio.run(ExternalClient(settings, get_provider(settings, "openthai")).request("bounded", b"png"))
    assert error.value.code == "EXTERNAL_INVALID_RESPONSE" and not parsed
