"""Shared and server-managed destinations with DNS-pinned, isolated HTTP."""
import asyncio
import base64
import hashlib
import ipaddress
import json
import logging
import os
import re
import socket
import time
from io import BytesIO
from urllib.parse import urlsplit

import httpcore
import httpx
import ijson
from httpcore._backends.auto import AutoBackend
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from app.core.config import MAX_DETECTION_REGIONS
from app.core.errors import AppError
from app.integrations.model_gateway import GatewayError, verified_tls_context
from app.pipelines.normalizers import bounded_text, confidence, geometry

logger = logging.getLogger(__name__)


class Provider(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    endpoint: str = Field(max_length=500)
    readiness_url: str | None = Field(default=None, max_length=500)
    request_format: str = Field(default="multipart", pattern="^(multipart|json_base64)$")
    image_field: str = Field(default="image", pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
    response_adapter: str = Field(default="openthai_v1", pattern="^(openthai_v1|text_json)$")
    text_path: str = Field(default="text", pattern=r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*){0,3}$", max_length=100)
    confidence_path: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*){0,3}$", max_length=100)
    auth_mode: str = Field(default="none", pattern="^(none|bearer|x_api_key|custom_header)$")
    auth_header: str = Field(default="X-API-Key", pattern="^(X-API-Key|X-Auth-Token|Api-Key)$")
    credential_env: str | None = Field(default=None, pattern=r"^EXTERNAL_OCR_SECRET_[A-Z0-9_]{1,60}$")
    timeout_seconds: float = Field(default=120, gt=0, le=240)
    max_response_bytes: int = Field(default=2 * 1024**2, ge=1024, le=8 * 1024**2)
    _credential_loader: object = PrivateAttr(default=None)
    _credential_configured: bool | None = PrivateAttr(default=None)
    _enabled: bool = PrivateAttr(default=True)
    _managed: bool = PrivateAttr(default=False)

    @model_validator(mode="after")
    def credential_contract(self):
        if self.auth_mode == "none" and self.credential_env is not None:
            raise ValueError("Unauthenticated providers cannot reference a credential")
        return self

    def public(self, provider_id):
        values = self.model_dump(exclude={"credential_env"})
        return {"id": provider_id, **values, "http_method": "POST",
                "managed": self._managed, "enabled": self._enabled,
                "api_key_configured": self._credential_configured if self._credential_configured is not None else bool(self.secret()) if self.auth_mode != "none" else False}

    def secret(self):
        if self._credential_loader is not None:
            try:
                return self._credential_loader()
            except AppError:
                raise GatewayError("External credential is unavailable", "EXTERNAL_CREDENTIAL_UNAVAILABLE") from None
        return os.environ.get(self.credential_env, "") if self.credential_env else ""

    def identity(self, provider_id):
        # Job snapshots pin all public routing/adapter semantics. Rotation may
        # change credentials without silently rerouting an interrupted Job.
        values = self.model_dump(exclude={"credential_env"})
        fingerprint = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
        return {"provider_id": provider_id, "provider_name": self.name,
                "adapter": self.response_adapter, "fingerprint": fingerprint}


def validate_url(url, development=False):
    parts = urlsplit(url)
    if (parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or "\\" in url or "%" in parts.netloc
            or any(ord(char) <= 32 or ord(char) >= 127 for char in url)):
        raise ValueError("Use an approved absolute URL without query, credentials or fragment")
    if parts.scheme != "https" and not (development and parts.hostname in {"localhost", "127.0.0.1", "::1"}):
        raise ValueError("HTTPS is required")
    if not parts.path.startswith("/") or ".." in parts.path.split("/"):
        raise ValueError("An exact endpoint path is required")
    parts.port  # Validate malformed/out-of-range ports.
    try:
        address = ipaddress.ip_address(parts.hostname)
    except ValueError:
        address = None
    if (address is not None and not allowed_ip(str(address), development)) or (parts.hostname == "localhost" and not development):
        raise ValueError("Private destination is blocked")
    return parts


def providers(settings, include_disabled=False):
    try:
        raw = json.loads(settings.external_ocr_providers.get_secret_value())
        if not isinstance(raw, dict) or len(raw) > 20:
            raise ValueError("Invalid registry")
        result = {}
        for key, value in raw.items():
            if not re.fullmatch(r"[a-z][a-z0-9_-]{0,49}", key):
                raise ValueError("Invalid provider ID")
            provider = Provider.model_validate(value)
            origin = validate_url(provider.endpoint, settings.external_ocr_development)
            if provider.readiness_url:
                ready = validate_url(provider.readiness_url, settings.external_ocr_development)
                if (origin.scheme, origin.hostname, origin.port) != (ready.scheme, ready.hostname, ready.port):
                    raise ValueError("Readiness must share the inference origin")
            result[key] = provider
    except (ValueError, TypeError):
        raise AppError("External OCR provider registry is invalid. Contact the server operator.", 503) from None
    factory = settings._external_provider_sessions
    if factory:
        from sqlalchemy import select

        from app.db.models import ExternalProvider
        from app.services.external_provider_service import provider_from_record
        with factory() as session:
            records = session.scalars(select(ExternalProvider).order_by(ExternalProvider.created_at))
            for record in records:
                if record.enabled or include_disabled:
                    result[record.id] = provider_from_record(record, settings)
    return result


def get_provider(settings, provider_id):
    provider = providers(settings).get(provider_id)
    if provider is None:
        raise AppError("Select an enabled external OCR provider", 422)
    return provider


def allowed_ip(address, development):
    ip = ipaddress.ip_address(address)
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    public = ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_unspecified)
    if ip.version == 6 and (ip.sixtofour or ip.teredo or ip.is_site_local or
            ip in ipaddress.ip_network("64:ff9b::/96") or ip in ipaddress.ip_network("64:ff9b:1::/48")):
        public = False
    return public or (development and ip.is_loopback)


class PinnedBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, development):
        self.development = development
        self.backend = AutoBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        try:
            answers = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(
                host, port, type=socket.SOCK_STREAM), timeout or 10)
            addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
            if not addresses or any(not allowed_ip(ip, self.development) for ip in addresses):
                raise httpcore.ConnectError("External destination is blocked")
            # Connect to the validated IP itself. HTTP Host and TLS SNI remain
            # the approved hostname. No second DNS lookup can rebind this socket.
            return await self.backend.connect_tcp(addresses[0], port, timeout, local_address, socket_options)
        except (OSError, TimeoutError, ValueError):
            raise httpcore.ConnectError("External DNS or connection failed") from None

    async def connect_unix_socket(self, *args, **kwargs):
        raise httpcore.ConnectError("Unix sockets are not permitted")

    async def sleep(self, seconds):
        await asyncio.sleep(seconds)


class ExternalClient:
    def __init__(self, settings, provider):
        self.settings, self.provider = settings, provider

    def client(self):
        transport = httpx.AsyncHTTPTransport(verify=verified_tls_context(), retries=0)
        # Pinned to httpx0.28/httpcore1.0. Integration tests exercise this path
        # over a real local TCP socket as well as transport-independent mocks.
        transport._pool._network_backend = PinnedBackend(self.settings.external_ocr_development)
        return httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False,
                                 timeout=httpx.Timeout(self.provider.timeout_seconds, connect=10))

    async def request(self, request_id, png=None):
        from app.core.external_quota import reserve
        quota = reserve(self.settings, "connection_checks" if png is None else "inference", 20 if png is None else 600)
        if not quota.connections.acquire(blocking=False):
            raise GatewayError("External request capacity reached", "EXTERNAL_HTTP_429", http_status=429, retry_after="5")
        try:
            return await self._request(request_id, png)
        finally:
            quota.connections.release()

    async def _request(self, request_id, png=None):
        provider = self.provider
        secret = provider.secret()
        if provider.auth_mode != "none" and not secret:
            raise GatewayError("External provider credential is unavailable", "EXTERNAL_MISSING_KEY")
        headers = {"X-Request-ID": request_id, "Accept-Encoding": "identity"}
        if provider.auth_mode == "bearer":
            headers["Authorization"] = "Bearer " + secret
        elif provider.auth_mode in {"x_api_key", "custom_header"}:
            headers[provider.auth_header if provider.auth_mode == "custom_header" else "X-API-Key"] = secret
        kwargs = {}
        if png is None:
            if not provider.readiness_url:
                return {"status": "configuration_valid", "message": "Configuration valid. Provider has no readiness endpoint. Inference has not been tested."}
            url, method = provider.readiness_url, "GET"
        else:
            if len(png) > self.settings.max_upload_mb * 1024**2:
                raise GatewayError("External input exceeds upload limit", "EXTERNAL_INPUT_TOO_LARGE")
            url, method = provider.endpoint, "POST"
            if provider.request_format == "multipart":
                kwargs["files"] = {provider.image_field: ("crop.png", BytesIO(png), "image/png")}
            else:
                kwargs["json"] = {provider.image_field: base64.b64encode(png).decode("ascii")}
        started = time.perf_counter()
        status = None
        try:
            async with asyncio.timeout(provider.timeout_seconds), self.client() as client:
                async with client.stream(method, url, headers=headers, **kwargs) as response:
                    status = response.status_code
                    if status != 200:
                        raise GatewayError("External provider request failed", f"EXTERNAL_HTTP_{status}",
                                           http_status=status, retry_after=response.headers.get("Retry-After"))
                    length = response.headers.get("content-length", "")
                    if length.isdecimal() and int(length) > provider.max_response_bytes:
                        raise GatewayError("External response exceeds limit", "EXTERNAL_RESPONSE_TOO_LARGE")
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise GatewayError("Compressed external responses are unsupported", "EXTERNAL_INVALID_RESPONSE")
                    body = bytearray()
                    async for chunk in response.aiter_bytes(65536):
                        if len(body) + len(chunk) > provider.max_response_bytes:
                            raise GatewayError("External response exceeds limit", "EXTERNAL_RESPONSE_TOO_LARGE")
                        body.extend(chunk)
                    if secret and secret.encode() in body:
                        raise GatewayError("External response contains credential material", "EXTERNAL_INVALID_RESPONSE")
                    # Bound container/object counts before json.loads allocates a
                    # Python graph. A byte limit alone permits millions of atoms.
                    depth = 0
                    with BytesIO(body) as source:
                        for count, (event, value) in enumerate(ijson.basic_parse(source), 1):
                            if event in {"start_map", "start_array"}:
                                depth += 1
                            elif event in {"end_map", "end_array"}:
                                depth -= 1
                            if count > 50000 or depth > 32:
                                raise ValueError("External JSON structure exceeds limits")
                            if secret and isinstance(value, str) and secret in value:
                                raise ValueError("External JSON contains credential material")
                    payload = json.loads(body)
                    if not isinstance(payload, dict):
                        raise ValueError("Expected object")
                    if png is None:
                        if payload.get("status") not in {"ready", "ok"}:
                            return {"status": "reachable", "message": "HTTP200 and authentication accepted. Readiness contract unconfirmed. Inference has not been tested."}
                        return {"status": "provider_ready", "message": "Provider reports ready and authentication accepted. Inference has not been tested."}
                    return payload
        except (TimeoutError, httpx.TimeoutException):
            raise GatewayError("External provider timed out", "EXTERNAL_TIMEOUT") from None
        except httpx.HTTPError:
            raise GatewayError("External provider connection failed or destination blocked", "EXTERNAL_UNAVAILABLE") from None
        except (ValueError, RecursionError, ijson.JSONError):
            raise GatewayError("External provider returned invalid JSON", "EXTERNAL_INVALID_RESPONSE") from None
        finally:
            if "files" in kwargs:
                kwargs["files"][provider.image_field][1].close()
            logger.info("external_ocr request_id=%s method=%s status=%s duration_ms=%.1f",
                        request_id, method, status, (time.perf_counter()-started)*1000)


def path_value(data, path):
    for part in path.split("."):
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


def _exact_count(value):
    return type(value) is int


def openthai_document(data):
    """Return one OpenThai document from a single body or a one-image batch body.

    OCRLab submits one image. A batch envelope must identify that image as index 0.
    A nested copy, a leaf-inference envelope, or an error item is not OCR text.
    """
    if "text" in data:
        return data
    if "results" not in data:
        raise GatewayError("OpenThai response text is missing or not a string", "INVALID_OCR_RESPONSE")
    results = data.get("results")
    total, succeeded, failed = data.get("total"), data.get("succeeded"), data.get("failed")
    shaped = (_exact_count(total) and _exact_count(succeeded) and _exact_count(failed)
              and isinstance(results, list) and total == len(results) and succeeded + failed == total
              and all(isinstance(item, dict) and _exact_count(item.get("index")) and item.get("status") in {"success", "error"}
                      for item in results))
    if not shaped:
        raise GatewayError("OpenThai response is not a single text result or a batch item", "INVALID_OCR_RESPONSE")
    if total != 1:
        raise GatewayError("Batch result count does not match input images", "INVALID_OCR_RESPONSE")
    item = results[0]
    if item["index"] != 0:
        raise GatewayError("Batch result index does not match the input image", "INVALID_OCR_RESPONSE")
    if item["status"] == "error" and item.get("result") is None and succeeded == 0 and failed == 1:
        error = item.get("error") if isinstance(item.get("error"), dict) else {}
        code = error.get("code")
        suffix = f": {code}" if isinstance(code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code) else ""
        raise GatewayError(f"OpenThai batch item failed{suffix}", "INVALID_OCR_RESPONSE")
    result = item.get("result")
    if item["status"] != "success" or not isinstance(result, dict) or item.get("error") is not None or succeeded != 1 or failed != 0:
        raise GatewayError("OpenThai batch item is not a successful OCR result", "INVALID_OCR_RESPONSE")
    return result


def normalize_external(payload, provider, crop, roi):
    boxes = []
    meta = {}
    if provider.response_adapter == "text_json":
        text = bounded_text(path_value(payload, provider.text_path))
        score = confidence(path_value(payload, provider.confidence_path)) if provider.confidence_path else None
    else:
        data, meta = payload.get("data"), payload.get("meta", {})
        if not isinstance(data, dict) or not isinstance(meta, dict):
            raise GatewayError("External response contract mismatch", "EXTERNAL_INVALID_RESPONSE")
        data = openthai_document(data)
        text, score = bounded_text(data.get("text")), confidence(data.get("confidence"))
        lines = data.get("lines", [])
        if not isinstance(lines, list) or len(lines) > MAX_DETECTION_REGIONS:
            raise GatewayError("External lines exceed contract limits", "EXTERNAL_INVALID_RESPONSE")
        if data.get("image") and data["image"] != {"width": crop.width, "height": crop.height}:
            raise GatewayError("External image coordinate frame mismatch", "EXTERNAL_INVALID_RESPONSE")
        for line in lines:
            if not isinstance(line, dict):
                raise GatewayError("External line is invalid", "EXTERNAL_INVALID_RESPONSE")
            bounded_text(line.get("text"))
            box = line.get("box")
            if box is None:
                continue
            if (not isinstance(box, list) or len(box) != 4 or
                    any(not isinstance(point, list) or len(point) != 2 for point in box)):
                raise GatewayError("External geometry is invalid", "EXTERNAL_INVALID_RESPONSE")
            mapped = geometry({"polygon": box, "text": line["text"], "confidence": line.get("confidence")},
                              (roi["x1"], roi["y1"]) if roi else (0, 0), (crop.width, crop.height))
            if mapped is None:
                raise GatewayError("External geometry is invalid", "EXTERNAL_INVALID_RESPONSE")
            boxes.append(mapped)
    # Keep provider reading order and full text, including multi-column pages.
    return text, score, boxes, meta
