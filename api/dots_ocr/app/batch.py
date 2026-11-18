import asyncio
import json
import time

from starlette.datastructures import UploadFile

from app.errors import ServiceError


async def uploaded_files(request, settings, batch):
    """The form context owns and closes every spooled upload, including errors."""
    if (
        not request.headers.get("content-type", "")
        .lower()
        .startswith("multipart/form-data;")
    ):
        raise ServiceError("MULTIPART_REQUIRED", "Use multipart/form-data.", 415)
    field = "images" if batch else "image"
    limit = settings.max_batch_images if batch else 1
    async with request.form(max_files=limit, max_fields=0, max_part_size=1024) as form:
        items = list(form.multi_items())
        if not items or any(
            key != field or not isinstance(value, UploadFile) for key, value in items
        ):
            raise ServiceError(
                "INVALID_UPLOAD_FIELDS", f"Upload using only the {field} file field."
            )
        if len(items) > limit:
            raise ServiceError("BATCH_TOO_LARGE", "Too many uploaded images.", 413)
        contents, total = [], 0
        for _, upload in items:
            data = await upload.read(settings.max_upload_bytes + 1)
            total += len(data)
            if (
                len(data) > settings.max_upload_bytes
                or total > settings.max_batch_upload_bytes
            ):
                raise ServiceError(
                    "PAYLOAD_TOO_LARGE", "Image or batch exceeds the upload limit.", 413
                )
            contents.append(data)
        return contents


async def infer_one(inference, content, settings):
    # Shield native work: a timed-out/disconnected HTTP request must not release
    # the single model slot while its GPU/CPU forward pass is still running.
    future = inference.submit(content)
    result = await asyncio.wait_for(
        asyncio.shield(future), settings.inference_timeout_seconds
    )
    data = result.model_dump(mode="json")
    if len(json.dumps(data, ensure_ascii=False).encode()) > settings.max_response_bytes:
        raise ServiceError(
            "RESPONSE_TOO_LARGE", "Model result exceeds the response limit.", 502
        )
    return data


async def infer_batch(inference, contents, settings):
    results = []
    encoded_bytes = 0
    for index, content in enumerate(contents):
        started = time.monotonic()
        try:
            result = await infer_one(inference, content, settings)
            item = {
                "index": index,
                "status": "success",
                "result": result,
                "error": None,
            }
        except TimeoutError:
            # Native work may still be running. Do not pretend remaining items
            # were processed or start another model call on the same device.
            raise ServiceError(
                "INFERENCE_TIMEOUT", "Batch stopped after an inference deadline.", 504
            ) from None
        except ServiceError as error:
            item = {
                "index": index,
                "status": "error",
                "result": None,
                "error": {"code": error.code, "message": error.message},
            }
        item["duration_ms"] = round((time.monotonic() - started) * 1000, 3)
        encoded_bytes += len(json.dumps(item, ensure_ascii=False).encode())
        if encoded_bytes > settings.max_batch_response_bytes:
            raise ServiceError(
                "RESPONSE_TOO_LARGE", "Batch result exceeds the response limit.", 502
            )
        results.append(item)
    successes = sum(item["status"] == "success" for item in results)
    return {
        "results": results,
        "count": len(results),
        "succeeded": successes,
        "failed": len(results) - successes,
        "execution": "sequential_wrapper",
    }
