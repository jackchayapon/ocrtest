import asyncio
import hmac
import logging
import time
import uuid

from app.errors import ServiceError, error_response

logger = logging.getLogger("dots.requests")


class RequestBoundary:
    """Authenticate and bound requests before multipart parsing or inference."""

    def __init__(self, app, settings, inference):
        self.app, self.settings, self.inference = app, settings, inference
        self.active = False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = time.monotonic()
        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        path, method = scope["path"], scope["method"]
        headers = dict(scope["headers"])
        acquired, status, response_started = False, 500, False

        async def safe_send(message):
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started, status = True, message["status"]
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-request-id", request_id.encode()),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ]
            await send(message)

        try:
            if path != "/health":
                expected = self.settings.api_key.get_secret_value()
                if not expected:
                    raise ServiceError(
                        "AUTH_NOT_CONFIGURED",
                        "Service authentication is not configured.",
                        503,
                    )
                supplied = headers.get(b"authorization", b"")
                if not hmac.compare_digest(supplied, ("Bearer " + expected).encode()):
                    raise ServiceError(
                        "UNAUTHORIZED", "A valid Bearer API key is required.", 401
                    )
            if method == "POST":
                if self.active or (
                    self.inference.pending is not None
                    and not self.inference.pending.done()
                ):
                    raise ServiceError(
                        "SERVICE_BUSY", "One inference request is already active.", 429
                    )
                self.active, acquired = True, True
            batch = path == "/api/v1/ocr-text-batches"
            limit = (
                self.settings.max_batch_upload_bytes
                if batch
                else self.settings.max_upload_bytes
            ) + 65536
            try:
                content_length = int(headers.get(b"content-length", b"0"))
            except ValueError:
                raise ServiceError(
                    "INVALID_REQUEST", "Invalid Content-Length.", 400
                ) from None
            if content_length < 0 or content_length > limit:
                raise ServiceError(
                    "PAYLOAD_TOO_LARGE", "Request exceeds the upload limit.", 413
                )
            received = 0

            async def bounded_receive():
                nonlocal received
                message = await receive()
                if message["type"] == "http.request":
                    received += len(message.get("body", b""))
                    if received > limit:
                        raise ServiceError(
                            "PAYLOAD_TOO_LARGE",
                            "Request exceeds the upload limit.",
                            413,
                        )
                return message

            timeout = (
                self.settings.batch_timeout_seconds
                if batch
                else self.settings.request_timeout_seconds
            )
            await asyncio.wait_for(
                self.app(scope, bounded_receive, safe_send), timeout=timeout
            )
        except TimeoutError:
            if not response_started:
                await error_response(
                    ServiceError("REQUEST_TIMEOUT", "Request deadline exceeded.", 504),
                    request_id,
                )(scope, receive, safe_send)
        except ServiceError as error:
            if not response_started:
                await error_response(error, request_id)(scope, receive, safe_send)
        except Exception:
            # Never log headers, file names, OCR output, raw exception messages or tracebacks.
            if not response_started:
                await error_response(
                    ServiceError(
                        "INTERNAL_ERROR", "Request could not be processed.", 500
                    ),
                    request_id,
                )(scope, receive, safe_send)
        finally:
            if acquired:
                self.active = False
            # Use a fixed route label, never user-controlled paths/query values.
            route = (
                path
                if path
                in {
                    "/health",
                    "/api/v1/readiness",
                    "/api/v1/ocr-text",
                    "/api/v1/ocr-text-batches",
                }
                else "unknown"
            )
            logger.info(
                "request_id=%s route=%s status=%d duration_ms=%.2f",
                request_id,
                route,
                status,
                (time.monotonic() - started) * 1000,
            )
