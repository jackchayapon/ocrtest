"""Encode complete large saved results without a second whole-body JSON copy."""
import json

from fastapi.encoders import jsonable_encoder
from starlette.responses import StreamingResponse

from app.core.native_memory import release_native_memory


class OwnedJSONResponse(StreamingResponse):
    def __init__(self, content, size):
        super().__init__(content, media_type="application/json", headers={"Content-Length": str(size)})

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.body_iterator.aclose()


def bounded_json_response(value):
    def encoded():
        encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":"), default=jsonable_encoder)
        for chunk in encoder.iterencode(value):
            for start in range(0, len(chunk), 16 * 1024):
                yield chunk[start:start + 16 * 1024].encode("utf-8")

    # Validate/count before sending HTTP200. A second bounded pass costs CPU,
    # but avoids both the whole JSON unicode/bytes copy and a large file cache.
    size = sum(len(chunk) for chunk in encoded())

    async def stream():
        if size >= 512 * 1024:
            release_native_memory()
        buffer = bytearray()
        for chunk in encoded():
            if len(buffer) + len(chunk) > 64 * 1024:
                yield bytes(buffer)
                buffer.clear()
            buffer.extend(chunk)
        if buffer:
            yield bytes(buffer)

    return OwnedJSONResponse(stream(), size)
