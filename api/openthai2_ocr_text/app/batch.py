"""Bounded sequential API batching using the single shared native reader."""
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager, suppress

from fastapi.responses import Response
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import ClientDisconnect

from app.config import MODEL_REVISION
from app.errors import ServiceError

logger = logging.getLogger("openthai")

BATCH_REQUEST_OPENAPI = {"requestBody": {"required": True, "content": {
    "multipart/form-data": {"schema": {"type": "object", "required": ["images"], "properties": {
        "images": {"type": "array", "items": {"type": "string", "format": "binary"}, "minItems": 1, "maxItems": 16}
    }}}}}}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode()


@asynccontextmanager
async def multipart_form(request, settings, max_files=None):
    parser = MultiPartParser(request.headers, request.stream(),
        max_files=settings.max_batch_images if max_files is None else max_files,
        max_fields=0, max_part_size=settings.max_upload_bytes)
    try:
        form = await parser.parse()
        try:
            yield form
        finally:
            await form.close()
    finally:
        # Starlette only closes these handles on MultiPartException. Also cover
        # disconnects, body-limit errors and cancellation before FormData exists.
        # Negative-path tests protect this dependency on the parser's handle list.
        for handle in parser._files_to_close_on_error:
            handle.close()


async def disconnected(request):
    while True:
        message = await request.receive()
        if message["type"] == "http.disconnect":
            return
        await asyncio.sleep(.01)


async def read_item(upload, index, inference, settings, disconnect):
    try:
        content = await upload.read(settings.max_upload_bytes + 1)
        if len(content) > settings.max_upload_bytes:
            raise ServiceError("PAYLOAD_TOO_LARGE", "Image exceeds the upload limit.", 413)
        if disconnect.done():
            raise ServiceError("CLIENT_DISCONNECTED", "Client disconnected before batch completed.", 499)
        future = inference.submit(content)
        completed, _ = await asyncio.wait({future, disconnect}, return_when=asyncio.FIRST_COMPLETED)
        if disconnect in completed:
            raise ServiceError("CLIENT_DISCONNECTED", "Client disconnected before batch completed.", 499)
        result = await asyncio.shield(future)
        item = {"index": index, "status": "success", "result": result, "error": None}
        body = encoded(item)
        if len(body) > settings.max_response_bytes:
            raise ServiceError("OUTPUT_TOO_LARGE", "Model output exceeds the response limit.", 503)
        return body, True
    except ServiceError as error:
        if error.status in {429, 499}:
            raise
        failure = {"code": error.code, "message": error.message}
    except Exception:
        failure = {"code": "MODEL_INFERENCE_FAILED", "message": "The model could not read this image."}
    return encoded({"index": index, "status": "error", "result": None, "error": failure}), False


async def process_uploads(uploads, request, inference, settings, started):
    items = []
    size = succeeded = 0
    disconnect = asyncio.create_task(disconnected(request))
    try:
        for index, upload in enumerate(uploads):
            item_started = time.perf_counter()
            body, success = await read_item(upload, index, inference, settings, disconnect)
            size += len(body)
            if size > settings.max_batch_response_bytes:
                raise ServiceError("OUTPUT_TOO_LARGE", "Batch output exceeds the response limit.", 503)
            items.append(body)
            succeeded += int(success)
            logger.info("batch_image request_id=%s index=%d status=%s duration_ms=%.1f",
                request.state.request_id, index, "success" if success else "error", (time.perf_counter()-item_started)*1000)
    finally:
        disconnect.cancel()
        with suppress(asyncio.CancelledError):
            await disconnect
    count = len(uploads)
    counters = encoded({"total": count, "succeeded": succeeded, "failed": count-succeeded})
    metadata = encoded({"request_id": request.state.request_id, "api_version": "v1",
        "service": "openthai2-ocr-text", "model": "iapp/OpenThai2.0-OCR-Text",
        "model_revision": MODEL_REVISION, "duration_ms": round((time.perf_counter()-started)*1000, 2)})
    body = b'{"data":{"results":[' + b','.join(items) + b'],' + counters[1:] + b',"meta":' + metadata + b'}'
    if len(body) > settings.max_batch_response_bytes:
        raise ServiceError("OUTPUT_TOO_LARGE", "Batch output exceeds the response limit.", 503)
    return Response(body, media_type="application/json")


async def batch_ocr(request, inference, settings):
    if inference.reader is None:
        raise ServiceError("MODEL_NOT_READY", "The model is unavailable.", 503)
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        raise ServiceError("UNSUPPORTED_MEDIA_TYPE", "Use multipart/form-data.", 415)
    started = time.perf_counter()
    try:
        async with multipart_form(request, settings) as form:
            uploads = form.getlist("images")
            if not uploads or any(key != "images" or not isinstance(value, UploadFile) for key, value in form.multi_items()):
                raise ServiceError("IMAGES_REQUIRED", "Upload files using the images field.")
            if len(uploads) > settings.max_batch_images:
                raise ServiceError("TOO_MANY_IMAGES", "Batch exceeds the image count limit.", 413)
            if sum(upload.size or 0 for upload in uploads) > settings.max_batch_upload_bytes:
                raise ServiceError("PAYLOAD_TOO_LARGE", "Batch exceeds the upload limit.", 413)
            return await process_uploads(uploads, request, inference, settings, started)
    except ServiceError:
        raise
    except ClientDisconnect:
        raise ServiceError("CLIENT_DISCONNECTED", "Client disconnected during batch upload.", 499) from None
    except MultiPartException as error:
        if error.message.startswith("Too many files."):
            raise ServiceError("TOO_MANY_IMAGES", "Batch exceeds the image count limit.", 413) from None
        raise ServiceError("BAD_REQUEST", "Malformed multipart batch request.", 400) from None
    except (ValueError, RuntimeError, HTTPException):
        raise ServiceError("BAD_REQUEST", "Malformed multipart batch request.", 400) from None
