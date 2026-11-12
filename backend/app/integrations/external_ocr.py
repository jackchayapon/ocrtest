"""Operator-registered destinations with DNS-pinned, credential-isolated HTTP."""
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
from httpcore._backends.auto import AutoBackend
from pydantic import BaseModel, ConfigDict, Field, model_validator

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

    @model_validator(mode="after")
    def credential_contract(self):
        if (self.auth_mode == "none") != (self.credential_env is None):
            raise ValueError("Authentication requires exactly one server credential reference")
        return self

    def public(self, provider_id):
        values = self.model_dump(exclude={"credential_env"})
        return {"id": provider_id, **values, "http_method": "POST",
                "api_key_configured": bool(self.secret()) if self.auth_mode != "none" else False}

    def secret(self):
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
    return parts


def providers(settings):
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
        return result
    except (ValueError, TypeError):
        raise AppError("External OCR provider registry is invalid. Contact the server operator.", 503) from None


def get_provider(settings, provider_id):
    provider = providers(settings).get(provider_id)
    if provider is None:
        raise AppError("Select an approved external OCR provider", 422)
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
                return {"status": "configuration_valid", "message": "Approved configuration. Provider has no readiness endpoint. Inference has not been tested."}
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
                    payload = json.loads(body)
                    if not isinstance(payload, dict):
                        raise ValueError("Expected object")
                    if secret and secret in json.dumps(payload, ensure_ascii=False):
                        raise GatewayError("External response contains credential material", "EXTERNAL_INVALID_RESPONSE")
                    if png is None:
                        if payload.get("status") not in {"ready", "ok"}:
                            return {"status": "reachable", "message": "HTTP200 and authentication accepted. Readiness contract unconfirmed. Inference has not been tested."}
                        return {"status": "provider_ready", "message": "Provider reports ready and authentication accepted. Inference has not been tested."}
                    return payload
        except (TimeoutError, httpx.TimeoutException):
            raise GatewayError("External provider timed out", "EXTERNAL_TIMEOUT") from None
        except httpx.HTTPError:
            raise GatewayError("External provider connection failed or destination blocked", "EXTERNAL_UNAVAILABLE") from None
        except (ValueError, RecursionError):
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
