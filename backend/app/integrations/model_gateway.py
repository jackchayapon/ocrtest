"""Server-only client for the reference Model API Gateway; never logs request bodies."""

import asyncio
import base64
import json
import logging
import math
import random
import re
import socket
import ssl
import time
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from io import BytesIO
from tempfile import SpooledTemporaryFile
from urllib.parse import urlsplit
from uuid import uuid4

import certifi
import httpx
import ijson

from app.core.batching import IMAGE_BATCH_SIZE
from app.core.config import Settings
from app.core.runtime_metrics import memory_snapshot
from app.integrations.gateway_response import READ_CHUNK_BYTES, EnvelopeParser, redacted_key
from app.integrations.gateway_routes import UnavailableService, origin, resolve_endpoint

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def verified_tls_context():
    # The same immutable CA trust store is used by every leaf request. Loading
    # OpenSSL's certificate store per Field/region retained native allocations
    # across long Jobs. Connections/clients still have their own lifetimes.
    return ssl.create_default_context(cafile=certifi.where())


def streamed_uploads(request, owner):
    """HTTPX streams file objects in64KiB chunks; raw bytes are one giant write.

    Give each attempt its own read cursor and deterministic close, retaining the
    immutable canonical bytes. Never take ownership of caller-supplied file handles.
    """
    files = request.get("files")
    if not files:
        return request
    pairs = files.items() if isinstance(files, dict) else files
    streamed = []
    for name, part in pairs:
        if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], bytes):
            part = (part[0], owner.enter_context(BytesIO(part[1])), *part[2:])
        streamed.append((name, part))
    return {**request, "files": dict(streamed) if isinstance(files, dict) else streamed}


class GatewayError(Exception):
    def __init__(
        self,
        message: str,
        code: str = "GATEWAY_ERROR",
        request_id: str | None = None,
        http_status=None,
        details=None,
        retry_after=None,
    ):
        super().__init__(message)
        self.code = code
        self.request_id = request_id
        self.http_status = http_status
        self.details = details or []
        self.retry_after = retry_after


def retry_after_seconds(value):
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0, seconds) if math.isfinite(seconds) else None


def preserve_leaf_predictions(data):
    """Current CDGS raw-only contract: retain OCR scalars/geometry, never image tensors.

    Existing structured results remain authoritative. Do not invent missing results
    or turn a count/schema mismatch into successful OCR.
    """
    if not isinstance(data, dict) or data.get("contract_version") != "leaf-inference-v1":
        return
    kind = data.get("kind")
    if not isinstance(data.get("results"), list) and not isinstance(data.get("result"), dict):
        raw = data.get("raw_output")
        if kind in {"text_detection_batch", "text_recognition_batch"}:
            keys = ("dt_polys", "dt_scores") if kind == "text_detection_batch" else ("rec_text", "rec_score", "model")
            required = "dt_polys" if kind == "text_detection_batch" else "rec_text"
            expected_type = list if kind == "text_detection_batch" else str
            if not isinstance(raw, list) or len(raw) > IMAGE_BATCH_SIZE or len(raw) != data.get("count") or any(not isinstance(item, dict) or not isinstance(item.get(required), expected_type) for item in raw):
                raise GatewayError("Leaf result count or schema does not match input", "INVALID_OCR_RESPONSE", http_status=200)
            items = [{key: item[key] for key in keys if key in item} for item in raw]
            data["results"] = items
            if kind == "text_detection_batch":
                data["result"] = {"results": items}
    data.pop("raw_output", None)


def safe_response(value, secrets=()):
    """Retain OCR diagnostics, removing credentials and embedded image payloads."""
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            if redacted_key(key):
                output[key] = "[redacted]"
            else:
                output[key] = safe_response(item, secrets)
        return output
    if isinstance(value, list):
        return [safe_response(item, secrets) for item in value]
    if isinstance(value, str):
        if value.startswith("data:image/"):
            return "[redacted image]"
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[redacted]")
        return value
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


class ModelGatewayClient:
    active_requests = 0

    def __init__(self, settings: Settings, pipeline_id=None):
        self.settings = settings
        self.pipeline_id = pipeline_id
        self.base_url = (settings.model_gateway_base_url).rstrip("/")
        self.key = settings.model_gateway_api_key.get_secret_value().strip()

    def resolve_endpoint(self, endpoint, service=None):
        try:
            return resolve_endpoint(
                self.base_url, endpoint, self.settings.model_gateway_service_prefixes, service
            )
        except UnavailableService:
            raise GatewayError(
                "This Gateway service is unavailable",
                "GATEWAY_SERVICE_UNAVAILABLE",
            ) from None
        except ValueError:
            raise GatewayError(
                "Invalid Gateway URL, endpoint or service prefix", "INVALID_GATEWAY_ROUTE"
            ) from None

    @staticmethod
    def service_for(endpoint, params):
        path = urlsplit(str(endpoint)).path
        if path.endswith(("/health", "/readiness")):
            return "status"
        if path.endswith(("/document-layouts", "/layout-predictions")):
            return "layout"
        return {"paddle": "paddle", "custom": "custom"}.get(params.get("engine"), "det_rec")

    def _client(self, timeout=None):
        return httpx.AsyncClient(
            timeout=timeout or self.settings.model_gateway_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            # Linux autotuning otherwise charged ~11.8 MB of receive backlog
            # while rejecting an oversized response. Bound that kernel memory
            # without changing decoded-byte limits, TLS, routing or retries.
            transport=httpx.AsyncHTTPTransport(
                verify=verified_tls_context(), trust_env=False, retries=0,
                socket_options=[(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)],
            ),
        )

    def headers(self, request_id: str):
        if self.key and (
            not self.key.isascii() or any(ord(c) < 33 or ord(c) == 127 for c in self.key)
        ):
            raise GatewayError("Gateway API Key has invalid characters", "INVALID_GATEWAY_KEY")
        headers = {"X-Request-ID": request_id, "Accept": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        return headers

    def build_request(
        self,
        *,
        png: bytes,
        endpoint: str,
        query_params: dict,
        fields: dict,
        request_id: str,
        request_format: str = "multipart",
    ):
        if not self.base_url or not endpoint:
            raise GatewayError("Not Configured: set the Gateway URL and endpoint", "NOT_CONFIGURED")
        request = {
            "method": "POST",
            "url": self.resolve_endpoint(endpoint, self.service_for(endpoint, query_params)),
            "params": query_params,
            "headers": self.headers(request_id),
        }
        if request_format == "multipart":
            request["files"] = {"image": ("crop.png", png, "image/png")}
            request["data"] = {
                key: str(value).lower() if isinstance(value, bool) else str(value)
                for key, value in fields.items()
            }
        elif request_format == "json_base64":
            request["json"] = {
                "image": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
                **fields,
            }
        else:
            raise GatewayError(
                "This Gateway supports multipart or JSON Base64 image requests",
                "UNSUPPORTED_REQUEST_FORMAT",
            )
        return request

    async def send(self, request: dict):
        started, status, code = time.perf_counter(), None, None
        details = []
        retry_count = 0
        ModelGatewayClient.active_requests += 1
        try:
            if origin(request["url"]) != origin(self.base_url):
                raise ValueError("Unapproved host")
            service = self.service_for(request["url"], request.get("params", {}))
            if (
                service in self.settings.model_gateway_service_prefixes
                and self.settings.model_gateway_service_prefixes[service] is None
            ):
                raise GatewayError(
                    "This Gateway service is unavailable",
                    "GATEWAY_SERVICE_UNAVAILABLE",
                )
            # A base ending in /paddle also works without the optional prefix map.
            # Integrated inference on this deployment must be explicitly ready.
            if service in {"paddle", "custom"} and urlsplit(str(request["url"])).path.startswith(
                "/paddle/api/v1/"
            ):
                readiness = await self.status()
                key = "hutch_crop" if service == "paddle" else "mint"
                if readiness.get(key) != "available":
                    raise GatewayError(
                        "The integrated OCR service is not ready",
                        "GATEWAY_SERVICE_UNAVAILABLE",
                    )
            retry_started = time.monotonic()
            for attempt in range(3):
                try:
                    result = await self._send(request)
                    break
                except GatewayError as exc:
                    if exc.http_status != 429 or attempt == 2:
                        raise
                    delay = max(exc.retry_after or 0, 2 ** attempt + random.uniform(0, .5))
                    if time.monotonic() - retry_started + delay > 30:
                        raise
                    retry_count += 1
                    await asyncio.sleep(delay)
            status = 200
            return result
        except ValueError:
            code = "INVALID_GATEWAY_ROUTE"
            raise GatewayError(
                "Gateway request must remain on its configured origin", code
            ) from None
        except GatewayError as exc:
            status, code = exc.http_status, exc.code
            details = exc.details
            raise
        finally:
            try:
                self.log_request(request, started, status, code, details, retry_count)
            finally:
                ModelGatewayClient.active_requests -= 1

    def log_request(self, request, started, status, code, details=(), retry_count=0):
        categories = {
            401: "authentication",
            403: "authorization",
            404: "route_not_found",
            422: "request_contract",
            429: "rate_limit",
            502: "upstream",
            503: "upstream",
        }
        category = categories.get(
            status,
            "response_schema"
            if code in {"INVALID_RESPONSE", "INVALID_OCR_RESPONSE"}
            else "timeout"
            if code == "GATEWAY_TIMEOUT"
            else "connection"
            if code == "GATEWAY_UNAVAILABLE"
            else "gateway"
            if code
            else None,
        )
        # Never log unrestricted queries, headers, exception text, bodies or OCR responses.
        if code == "GATEWAY_SERVICE_UNAVAILABLE":
            category = "availability"  # Locally blocked; no inference HTTP status exists.
        elif code == "UPSTREAM_MODEL_ERROR":
            category = "upstream_model"
        event = dict(
            request_id=str(request.get("headers", {}).get("X-Request-ID", ""))[:100],
            pipeline_id=self.pipeline_id,
            service=self.service_for(request.get("url", ""), request.get("params", {})),
            endpoint_path=urlsplit(str(request.get("url", ""))).path,
            http_status=status,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            error_code=code,
            retry_count=retry_count,
            failure_category=category,
            model_selection={k: str(v)[:100] for k, v in request.get("params", {}).items()
                             if k in {"version", "model", "engine"}
                             and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", str(v))},
            batch_count=len(request.get("files", [])),
            error_details=details,
            active_gateway_tasks=ModelGatewayClient.active_requests,
            **memory_snapshot(),
        )
        logger.log(
            logging.WARNING if code else logging.INFO,
            "%s",
            json.dumps(
                safe_response(event, (self.key, self.settings.database_url.get_secret_value()))
            ),
        )

    async def _send(self, request: dict):
        if not self.key:
            raise GatewayError("ยังไม่ได้ตั้งค่า API Key สำหรับ Gateway", "MISSING_GATEWAY_KEY")
        try:
            async with self._client() as client, AsyncExitStack() as uploads:
                async with client.stream(**streamed_uploads(request, uploads)) as response:
                    if response.is_redirect:
                        raise GatewayError(
                            "Gateway redirect was blocked",
                            "GATEWAY_REDIRECT_BLOCKED",
                            http_status=response.status_code,
                        )
                    limit = self.settings.model_gateway_max_response_mb * 1024 * 1024
                    def oversized():
                        return GatewayError(
                            f"ผลลัพธ์ที่ Gateway ส่งกลับมีขนาดใหญ่เกินขีดจำกัด {self.settings.model_gateway_max_response_mb} MB",
                            "RESPONSE_TOO_LARGE",
                        )
                    length = response.headers.get("Content-Length", "").lstrip("0") or "0"
                    if (not response.headers.get("Content-Encoding") and length.isdecimal()
                            and (len(length.lstrip("0")) > 20 or int(length) > limit)):
                        raise oversized()
                    parser = EnvelopeParser(lambda value: safe_response(
                        value, (self.key, self.settings.database_url.get_secret_value())))
                    try:
                        # Bound RAM independently of body length. Spill only transient
                        # responses to an OS-private temporary file, never upload storage.
                        # Oversized bodies are rejected before any JSON token allocation.
                        with SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b") as body:
                            size = 0
                            async for chunk in response.aiter_bytes(chunk_size=READ_CHUNK_BYTES):
                                size += len(chunk)
                                if size > limit:
                                    raise oversized()
                                body.write(chunk)
                            body.seek(0)
                            while chunk := body.read(READ_CHUNK_BYTES):
                                parser.feed(chunk)
                            payload = parser.finish()
                    except (ijson.JSONError, ValueError, UnicodeDecodeError):
                        if response.is_error:
                            raise GatewayError(
                                f"Gateway request failed (HTTP {response.status_code})",
                                f"HTTP_{response.status_code}",
                                http_status=response.status_code,
                                retry_after=retry_after_seconds(response.headers.get("Retry-After")),
                            ) from None
                        raise GatewayError(
                            "Gateway returned invalid JSON",
                            "INVALID_RESPONSE",
                            http_status=response.status_code,
                        ) from None
                    except OSError:
                        raise GatewayError(
                            "Temporary Gateway response buffering is unavailable",
                            "RESPONSE_BUFFER_UNAVAILABLE",
                        ) from None
                    finally:
                        parser.close()
                    if response.is_error or isinstance(payload, dict) and "error" in payload:
                        error = payload.get("error", {}) if isinstance(payload, dict) else {}
                        if not isinstance(error, dict):
                            error = {}
                        code = str(
                            safe_response(
                                error.get("code", f"HTTP_{response.status_code}"), (self.key,)
                            )
                        )
                        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,80}", code):
                            code = "GATEWAY_ERROR"
                        rid = safe_response(
                            error.get("request_id"),
                            (self.key, self.settings.database_url.get_secret_value()),
                        )
                        details = []
                        for item in error.get("details", [])[:10] if isinstance(error.get("details"), list) else []:
                            if isinstance(item, dict):
                                # Do not reflect messages, input values or worker stack traces.
                                item = safe_response(item, (self.key, self.settings.database_url.get_secret_value()))
                                detail = {k: item[k] for k in ("code", "type")
                                          if isinstance(item.get(k), str)
                                          and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", item[k])}
                                if detail:
                                    details.append(detail)
                            if len(details) == 5:
                                break
                        messages = {
                            401: "Gateway authentication is required or invalid",
                            403: "Gateway access was denied",
                            429: "Gateway is rate limited; try again later",
                            503: "The requested Gateway service is unavailable",
                        }
                        raise GatewayError(
                            ("Gateway model worker failed; verify the model service using the request ID"
                             if code == "UPSTREAM_MODEL_ERROR" else messages.get(
                                response.status_code,
                                f"Gateway request failed (HTTP {response.status_code})",
                            )),
                            code,
                            str(rid)[:100] if rid else None,
                            http_status=response.status_code,
                            details=details,
                            retry_after=retry_after_seconds(response.headers.get("Retry-After")),
                        )
                    if (
                        not isinstance(payload, dict)
                        or "data" not in payload
                        or not isinstance(payload.get("meta"), dict)
                    ):
                        raise GatewayError(
                            "Gateway response is missing its data/meta envelope",
                            "INVALID_RESPONSE",
                            http_status=response.status_code,
                        )
                    # The Gateway contract is data/meta. Ignore extra transport archives before
                    # redaction and downstream batching can amplify their allocations.
                    data = payload["data"]
                    try:
                        preserve_leaf_predictions(data)
                    except GatewayError as exc:
                        rid = safe_response(payload["meta"].get("request_id"), (self.key, self.settings.database_url.get_secret_value()))
                        if isinstance(rid, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", rid):
                            exc.request_id = rid
                        raise
                    # Strings/images were sanitized during parsing; no second object tree.
                    return {"data": data, "meta": payload["meta"]}
        except httpx.TimeoutException:
            raise GatewayError("Gateway request timed out", "GATEWAY_TIMEOUT") from None
        except httpx.RequestError:
            raise GatewayError(
                "Gateway is unavailable; check the connection settings", "GATEWAY_UNAVAILABLE"
            ) from None

    def build_batch_request(self, *, pngs, endpoint, version, request_id):
        """Verified leaf batch contract: repeated multipart `images` parts, in order."""
        if not self.base_url or not pngs:
            raise GatewayError(
                "A Gateway URL and image batch are required", "INVALID_PIPELINE_INPUT"
            )
        return {
            "method": "POST",
            "url": self.resolve_endpoint(endpoint, "det_rec"),
            "params": {"version": str(version)},
            "headers": self.headers(request_id),
            "files": [
                ("images", (f"line-{index}.png", png, "image/png"))
                for index, png in enumerate(pngs)
            ],
        }

    async def status(self):
        output = {
            "gateway": "unavailable",
            "mint": "unknown",
            "hutch_crop": "unknown",
            "hutch_full": "unknown",
            "benchmark": "unknown",  # Readiness currently does not report the leaf DET/REC services.
            "hutch_fine_tune_v2": "unknown",
            "thai_ft_v2": "unknown",  # No variant-specific readiness is reported upstream.
            "auto_roi": "unknown",
            "api_key_configured": bool(self.key),
            "services": {},  # Deployment readiness, not per-model/variant readiness.
        }
        if not self.base_url:
            return {**output, "gateway": "not_configured"}
        try:
            headers = self.headers(f"status_{uuid4().hex}")
            async with self._client(timeout=10) as client:
                health = await self.status_get(client, "/api/v1/health", headers)
                if health.is_success:
                    output["gateway"] = "connected"
                response = await self.status_get(client, "/api/v1/readiness", headers)
                if response.status_code in (401, 403):
                    return {
                        **output,
                        **dict.fromkeys(
                            (
                                "mint",
                                "hutch_crop",
                                "hutch_full",
                                "benchmark",
                                "thai_ft_v2",
                                "hutch_fine_tune_v2",
                                "auto_roi",
                            ),
                            "not_authenticated",
                        ),
                        "message": "Readiness requires valid Gateway authentication.",
                    }
                payload = response.json()
                data = payload.get("data", {})
                services = data.get("services", []) if isinstance(data, dict) else []
                if not services:
                    for detail in payload.get("error", {}).get("details", []):
                        if isinstance(detail, dict):
                            services.extend(detail.get("services", []))
                names = {
                    "ocr-custom": ("mint",),
                    "ocr-paddle": ("hutch_crop", "hutch_full"),
                    "layout": ("auto_roi",),
                }
                inventory = {
                    "text-detection": "det",
                    "text-recognition": "rec",
                    "layout-model": "layout_leaf",
                    "layout": "layout_pipeline",
                    "table-model": "table_v2",
                }
                for service in services:
                    if service.get("name") in inventory:
                        output["services"][inventory[service["name"]]] = (
                            "available" if service.get("status") == "ready" else "unavailable"
                        )
                    for key in names.get(service.get("name"), ()):
                        output[key] = (
                            "available" if service.get("status") == "ready" else "unavailable"
                        )
                for name, keys in {
                    "paddle": ("hutch_crop", "hutch_full"),
                    "custom": ("mint",),
                }.items():
                    if (
                        name in self.settings.model_gateway_service_prefixes
                        and self.settings.model_gateway_service_prefixes[name] is None
                    ):
                        for key in keys:
                            output[key] = "unavailable"
                if response.is_success:
                    output["gateway"] = "connected"
                output["message"] = (
                    "Readiness reports deployed services; unknown services were not reported."
                )
                return output
        except (httpx.HTTPError, GatewayError, ValueError, AttributeError, TypeError):
            return {**output, "message": "Gateway readiness could not be verified."}

    async def status_get(self, client, endpoint, headers):
        request = dict(url=self.resolve_endpoint(endpoint, "status"), headers=headers)
        started, response, code = time.perf_counter(), None, None
        try:
            response = await client.get(**request)
            if not response.is_success:
                code = f"HTTP_{response.status_code}"
            return response
        except httpx.TimeoutException:
            code = "GATEWAY_TIMEOUT"
            raise
        except httpx.HTTPError:
            code = "GATEWAY_UNAVAILABLE"
            raise
        finally:
            self.log_request(
                request, started, response.status_code if response is not None else None, code
            )
