"""Server-only client for the reference Model API Gateway; never logs request bodies."""

import base64
import json
import math
import re
from uuid import uuid4

import httpx

from app.core.config import Settings


class GatewayError(Exception):
    def __init__(self, message: str, code: str = "GATEWAY_ERROR", request_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.request_id = request_id


def safe_response(value, secrets=()):
    """Retain OCR diagnostics, removing credentials and embedded image payloads."""
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(
                part in lowered
                for part in ("api_key", "apikey", "authorization", "password", "token")
            ) or lowered in {
                "image",
                "images",
                "input_img",
                "output_img",
                "image_base64",
                "image_data",
                "base64",
                "input_image",
                "database_url",
            }:
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
    def __init__(self, settings: Settings, base_url: str | None = None, api_key: str | None = None):
        self.settings = settings
        self.base_url = (
            base_url if base_url is not None else settings.model_gateway_base_url
        ).rstrip("/")
        self.key = (
            api_key if api_key is not None else settings.model_gateway_api_key.get_secret_value()
        )

    def _client(self, timeout=None):
        return httpx.AsyncClient(
            timeout=timeout or self.settings.model_gateway_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        )

    def headers(self, request_id: str):
        headers = {"X-Request-ID": request_id, "Accept": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        return headers

    def build_full_roi_request(self, *, source, endpoint, query_params, fields, request_id):
        """Integration boundary only: inspected upstream does not consume logical ROI.

        Implement serialization here only after a verified external ROI contract exists.
        Arbitrary multipart fields accepted by the gateway are not proof of ROI support.
        """
        raise GatewayError(
            "ยังไม่ยืนยันรูปแบบส่ง ROI ให้ Hutch Full จึงยังเรียกบริการนี้ไม่ได้",
            "ROI_CONTRACT_UNCONFIRMED",
        )

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
            "url": self.base_url + endpoint,
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
        if not self.key:
            raise GatewayError("ยังไม่ได้ตั้งค่า API Key สำหรับ Gateway", "MISSING_GATEWAY_KEY")
        try:
            async with self._client() as client:
                async with client.stream(**request) as response:
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 16 * 1024 * 1024:
                            raise GatewayError(
                                "Gateway response exceeds the 16 MB limit", "RESPONSE_TOO_LARGE"
                            )
                    try:
                        payload = json.loads(body)
                    except (ValueError, UnicodeDecodeError):
                        raise GatewayError(
                            "Gateway returned invalid JSON", "INVALID_RESPONSE"
                        ) from None
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
                        messages = {
                            401: "Gateway authentication is required or invalid",
                            403: "Gateway access was denied",
                            429: "Gateway is rate limited; try again later",
                            503: "The requested Gateway service is unavailable",
                        }
                        raise GatewayError(
                            messages.get(
                                response.status_code,
                                f"Gateway request failed (HTTP {response.status_code})",
                            ),
                            code,
                            str(rid)[:100] if rid else None,
                        )
                    if (
                        not isinstance(payload, dict)
                        or "data" not in payload
                        or not isinstance(payload.get("meta"), dict)
                    ):
                        raise GatewayError(
                            "Gateway response is missing its data/meta envelope", "INVALID_RESPONSE"
                        )
                    return safe_response(
                        payload, (self.key, self.settings.database_url.get_secret_value())
                    )
        except httpx.TimeoutException:
            raise GatewayError("Gateway request timed out", "GATEWAY_TIMEOUT") from None
        except httpx.RequestError:
            raise GatewayError(
                "Gateway is unavailable; check the connection settings", "GATEWAY_UNAVAILABLE"
            ) from None

    async def status(self):
        output = {
            "gateway": "unavailable",
            "mint": "unknown",
            "hutch_crop": "unknown",
            "hutch_full": "contract_unconfirmed",
            "auto_roi": "unknown",
            "api_key_configured": bool(self.key),
        }
        if not self.base_url:
            return {**output, "gateway": "not_configured"}
        headers = self.headers(f"status_{uuid4().hex}")
        try:
            async with self._client(timeout=10) as client:
                health = await client.get(self.base_url + "/api/v1/health", headers=headers)
                if health.is_success:
                    output["gateway"] = "connected"
                response = await client.get(self.base_url + "/api/v1/readiness", headers=headers)
                if response.status_code in (401, 403):
                    return {
                        **output,
                        **dict.fromkeys(
                            ("mint", "hutch_crop", "hutch_full", "auto_roi"), "not_authenticated"
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
                    "ocr-paddle": ("hutch_crop",),
                    "layout": ("auto_roi",),
                }
                for service in services:
                    for key in names.get(service.get("name"), ()):
                        output[key] = (
                            "available" if service.get("status") == "ready" else "unavailable"
                        )
                if response.is_success:
                    output["gateway"] = "connected"
                output["message"] = (
                    "Readiness reports deployed services; unknown services were not reported."
                )
                return output
        except (httpx.HTTPError, ValueError, AttributeError, TypeError):
            return {**output, "message": "Gateway readiness could not be verified."}
