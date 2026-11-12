"""Fixed shared budgets for the existing one-process/one-replica deployment."""
import asyncio
from threading import BoundedSemaphore, Lock
from time import monotonic

from starlette.responses import JSONResponse

from app.core.errors import AppError

_creation_lock = Lock()


class SharedQuota:
    def __init__(self, clock=monotonic):
        self.clock = clock
        self.windows = {}
        self.lock = Lock()
        self.connections = BoundedSemaphore(2)

    def reserve(self, scope, limit):
        with self.lock:
            current = self.clock()
            start, count = self.windows.get(scope, (current, 0))
            if current - start >= 60:
                start, count = current, 0
            if count >= limit:
                error = AppError("Shared external API quota reached. Try again later.", 429)
                error.retry_after = max(1, round(60 - (current - start)))
                raise error
            self.windows[scope] = (start, count + 1)


def reserve(settings, scope, limit):
    with _creation_lock:
        if settings._external_shared_quota is None:
            settings._external_shared_quota = SharedQuota()
        quota = settings._external_shared_quota
    quota.reserve(scope, limit)
    return quota


class ExternalConfigGuard:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "DELETE"}
                or not scope["path"].startswith(("/api/external-providers", "/api/external-pipelines"))):
            return await self.app(scope, receive, send)
        started = False
        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)
        try:
            reserve(self.settings, "configuration", 30)
            # Read before FastAPI's JSON parser, which otherwise converts receive
            # exceptions into HTTP400. Keep total time and allocation bounded.
            body = bytearray()
            async with asyncio.timeout(10):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    if len(body) + len(message.get("body", b"")) > 65536:
                        raise AppError("External provider configuration exceeds the body limit", 413)
                    body.extend(message.get("body", b""))
                    if not message.get("more_body", False):
                        break
            pending = True
            async def buffered_receive():
                nonlocal pending
                if pending:
                    pending = False
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()
            await self.app(scope, buffered_receive, tracked_send)
        except AppError as error:
            if not started:
                await JSONResponse({"detail": error.message}, status_code=error.status_code,
                    headers={"Retry-After": str(getattr(error, "retry_after", 60))} if error.status_code == 429 else {})(scope, receive, send)
        except TimeoutError:
            if not started:
                await JSONResponse({"detail": "Configuration upload timed out"}, status_code=408)(scope, receive, send)
