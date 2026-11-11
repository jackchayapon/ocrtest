"""Bounded stored-preview reads; PDF rendering still owns image admission.

The cache is disposable, private and capped at8MiB/16files. It never replaces
the source or enters the OCR execution path. Cached pages retain exact pixels.
"""
import hashlib
from pathlib import Path
from tempfile import NamedTemporaryFile

from starlette.responses import StreamingResponse

from app.core.errors import AppError

CACHE_BYTES = 8 * 1024 * 1024


class PreviewResponse(StreamingResponse):
    def __init__(self, source, lock):
        self.source, self.lock = source, lock
        def chunks():
            while part := source.read(64 * 1024):
                yield part
        super().__init__(chunks(), media_type="image/png", headers={
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

    async def __call__(self, scope, receive, send):
        try:
            if self.lock.locked():
                from app.core.workload import WorkloadGuard
                return await WorkloadGuard.busy(scope, receive, send)
            async with self.lock:
                await super().__call__(scope, receive, send)
        finally:
            self.source.close()


class PreviewService:
    def __init__(self, cases):
        self.cases = cases

    def cache_path(self, document, page):
        identity = f"{document.id}:{document.sha256}:{page}:{document.pdf_render_dpi}"
        return Path(self.cases.storage.root) / ".preview-cache" / (hashlib.sha256(identity.encode()).hexdigest()+".png")

    def store(self, target, data):
        if len(data) > CACHE_BYTES:
            return
        temporary = None
        try:
            target.parent.mkdir(exist_ok=True)
            with NamedTemporaryFile(dir=target.parent, suffix=".tmp", delete=False) as temp:
                temporary = Path(temp.name)
                temp.write(data)
            temporary.replace(target)
            files = sorted(target.parent.glob("*.png"), key=lambda p: p.stat().st_mtime)
            total = sum(p.stat().st_size for p in files)
            remaining = len(files)
            for path in files:
                if total <= CACHE_BYTES and remaining <= 16:
                    break
                if path == target:
                    continue
                size = path.stat().st_size
                try:
                    path.unlink()
                    total -= size
                    remaining -= 1
                except PermissionError:
                    # Windows may hold an active reader. Never affect the source.
                    pass
        except OSError:
            # Cache is optional. A full/unwritable cache must not alter sources
            # or turn an otherwise valid bounded preview into a server failure.
            pass
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    async def source(self, document, selected, image_lock):
        limit = self.cases.settings.max_upload_mb * 1024 * 1024 + self.cases.settings.max_image_pixels * 4
        if selected is None:
            self.cases.images.inspect(self.cases.storage.read_prefix(document.storage_key, 65536))
            return self.cases.storage.open_bounded(document.storage_key, limit)
        if not self.cases.storage.exists(document.storage_key):
            raise AppError("Stored image is unavailable", 404)
        target = self.cache_path(document, selected)
        try:
            return target.open("rb")
        except FileNotFoundError:
            pass
        if image_lock.locked():
            raise AppError("กำลังเตรียมภาพ กรุณารอและลองใหม่ / Preview processing busy", 429)
        async with image_lock:
            data = self.cases.image_bytes(document.id, page_number=selected)
            self.store(target, data)
            if target.exists():
                return target.open("rb")
            from io import BytesIO
            return BytesIO(data)

    async def response(self, document_id, page, request):
        document = self.cases.repository.document(document_id)
        selected = self.cases.page_number(document, page)
        source = await self.source(document, selected, request.app.state.image_lock)
        return PreviewResponse(source, request.app.state.preview_read_lock)

    async def metadata(self, document_id, page, request):
        from app.services.serializers import document_json
        document = self.cases.repository.document(document_id)
        selected = self.cases.page_number(document, page)
        if selected is None:
            return document_json(document)
        with await self.source(document, selected, request.app.state.image_lock) as source:
            width, height = self.cases.images.inspect(source.read(65536))
        return document_json(document, selected, (width, height))
