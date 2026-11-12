import asyncio
import hmac
import logging
import time
from uuid import uuid4

from starlette.datastructures import Headers

from app.errors import ServiceError, error_response


def authenticate(headers, key):
    if not key:
        return
    bearer = headers.get("authorization", "")
    value = bearer[7:] if bearer.startswith("Bearer ") else headers.get("x-api-key", "")
    if not hmac.compare_digest(value.encode(), key.encode()):
        raise ServiceError("UNAUTHORIZED", "A valid API key is required.", 401)


class RequestControls:
    """Admit before parsing and preserve the native slot across HTTP deadlines."""
    def __init__(self, app, settings, inference):
        self.app, self.settings, self.inference = app, settings, inference
        self.admitted = False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = "req_" + uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        owns_slot = response_started = False
        status = 500
        headers = Headers(scope=scope)

        async def send_headers(message):
            nonlocal response_started, status
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                message["headers"] = [(key, value) for key, value in message.get("headers", []) if key.lower() != b"x-request-id"]
                message["headers"].append((b"x-request-id", request_id.encode()))
            await send(message)

        received = 0
        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.settings.max_upload_bytes + 65536:
                raise ServiceError("PAYLOAD_TOO_LARGE", "Request exceeds the body limit.", 413)
            return message

        error = None
        try:
            if scope["path"].startswith("/api/"):
                authenticate(headers, self.settings.api_key.get_secret_value())
            if scope["method"] == "POST":
                if self.admitted or (self.inference.pending and not self.inference.pending.done()):
                    raise ServiceError("SERVICE_BUSY", "The inference slot is occupied.", 429)
                self.admitted = owns_slot = True
                size = headers.get("content-length")
                if size and (not size.isdecimal() or int(size) > self.settings.max_upload_bytes + 65536):
                    raise ServiceError("PAYLOAD_TOO_LARGE", "Request exceeds the body limit.", 413)
            await asyncio.wait_for(self.app(scope, bounded_receive, send_headers), self.settings.request_timeout_seconds)
        except ServiceError as failure:
            error = failure
        except TimeoutError:
            error = ServiceError("REQUEST_TIMEOUT", "Processing deadline exceeded.", 504)
        except Exception as failure:
            logging.getLogger("openthai").error("request_failed request_id=%s category=%s", request_id, type(failure).__name__)
            error = ServiceError("INTERNAL_ERROR", "Processing failed.", 500)
        finally:
            if owns_slot:
                self.admitted = False
        if error and not response_started:
            await error_response(error, request_id)(scope, receive, send_headers)
        path = scope["path"] if scope["path"] in {"/health", "/api/v1/readiness", "/api/v1/ocr-text"} else "unmatched"
        logging.getLogger("openthai").info("request_id=%s path=%s status=%s duration_ms=%.1f", request_id,
                                         path, status, (time.perf_counter()-started)*1000)
