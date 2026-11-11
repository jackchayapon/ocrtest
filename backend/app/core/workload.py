"""Process-local allocation admission; database queue owns durable OCR work."""
import asyncio

from fastapi import HTTPException
from starlette.responses import JSONResponse


class WorkloadGuard:
    def __init__(self, app, lock, settings):
        self.app, self.lock, self.settings = app, lock, settings
        self.submission_lock = asyncio.Lock()
        self.waiters = {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] == "OPTIONS":
            return await self.app(scope, receive, send)
        path, method = scope["path"], scope["method"]
        # Include multipart framing, but never read arbitrary bodies into memory.
        limit = (self.settings.max_upload_mb * 1024 * 1024 + 65536
                 if path == "/api/documents" and method == "POST" else 1024 * 1024)
        headers = dict(scope.get("headers", []))
        length = headers.get(b"content-length", b"0")
        if not length.isdigit() or int(length) > limit:
            return await JSONResponse({"detail": "คำขอใหญ่เกินกำหนด / Request body too large"}, 413)(scope, receive, send)
        read = 0

        async def bounded_receive():
            nonlocal read
            message = await receive()
            read += len(message.get("body", b""))
            if read > limit:
                raise HTTPException(413, "คำขอใหญ่เกินกำหนด / Request body too large")
            return message

        # Polling, saved results and GT remain available while an image is in use.
        submission = path.endswith("/jobs") and method == "POST"
        # Stored PNG/cached PDF reads stream without decoding. Cache misses in
        # the document routes still take this same image lock before rendering.
        document_work = path.startswith("/api/documents") and (method != "GET" or path.endswith("/crop"))
        heavy = (submission or document_work or path == "/api/dataset/export"
                 or (path == "/api/test-cases" and method == "POST")
                 or path.endswith(("/run", "/evaluation-report", "/evaluation-excel")))
        if not heavy:
            return await self.app(scope, bounded_receive, send)
        lock = self.submission_lock if submission else self.lock
        acquired = False
        if lock.locked() and self.waiters.get(lock, 0) >= 1:
            return await self.busy(scope, receive, send)
        self.waiters[lock] = self.waiters.get(lock, 0) + 1
        try:
            try:
                await asyncio.wait_for(lock.acquire(), timeout=2)
                acquired = True
            except TimeoutError:
                return await self.busy(scope, receive, send)
            finally:
                self.waiters[lock] -= 1
            # Hold admission through streaming and disconnect cleanup, not only headers.
            await self.app(scope, bounded_receive, send)
        finally:
            if acquired:
                lock.release()

    @staticmethod
    async def busy(scope, receive, send):
        await JSONResponse(
            {"detail": "ระบบกำลังประมวลผลภาพ กรุณาลองใหม่ / Image processing busy; retry later"},
            429, headers={"Retry-After": "5", "X-OCRLab-Retry-Safe": "pre-admission"},
        )(scope, receive, send)
