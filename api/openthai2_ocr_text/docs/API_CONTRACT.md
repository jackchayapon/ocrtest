# HTTP contract v1

`GET /health` returns HTTP200 `{"status":"alive"}` without inference. `GET /api/v1/readiness` returns HTTP200 with `status=ready` after successful loading, or HTTP503 `MODEL_NOT_READY`. Readiness and inference require the configured API key. Model loading failures leave liveness operational for diagnosis.

The service requires a nonempty printable-ASCII `OPENTHAI_API_KEY` without whitespace. An unset, empty or unusable value skips model loading and fails protected APIs with503 `AUTH_NOT_CONFIGURED`. Liveness remains available. Compose rejects an empty/unset value before startup. Existing valid-key Bearer and X-API-Key requests retain their contracts. Gateway-client and upstream-service keys are an owner-approved configuration decision.

`POST /api/v1/ocr-text` accepts exactly one multipart file named `image`. PNG and JPEG content are accepted regardless of filename. Default upload limit is 10 MiB, request body limit is upload limit plus64 KiB, pixel limit2,000,000 and maximum dimension8000. The request deadline defaults120 seconds. These service limits are operator-configurable. One request is admitted before multipart parsing and inference. Other POSTs receive429 with `Retry-After: 5`.

Success has the following shape. Values below illustrate the contract.

```json
{"data":{"text":"ข้อความ","lines":[{"text":"ข้อความ","confidence":0.98,"row":0,"box":[[1,2],[80,2],[80,30],[1,30]]}],"confidence":null,"geometry_available":true,"image":{"width":300,"height":200},"rotation":0,"text_angle":0},"meta":{"request_id":"req_generated","api_version":"v1","service":"openthai2-ocr-text","model":"iapp/OpenThai2.0-OCR-Text","model_revision":"39fa41bdd49f067ba41b1d9de79c06ab506d67d4","duration_ms":120}}
```

Full text follows model reading order. Polygon coordinates use original input pixels, after the runtime's inverse rotation/deskew. Confidence is nullable per line and always null at aggregate level. Empty inference returns empty text and lines with `geometry_available=false`. The API bounds lines1024, text32768 characters and serialized response2 MiB by default.

Each `line.box` contains exactly four finite `[x,y]` pairs. Coordinates and `text_angle` must remain finite after numeric coercion. The wrapper preserves model coordinates. It does not scale, rotate, clamp or add a document ROI offset. A consuming document adapter adds a crop offset once. [Verified Single/Batch selection and diagnostics](RESPONSE_MAPPING.md).

Errors share this envelope.

```json
{"error":{"code":"INVALID_IMAGE","message":"The uploaded image is invalid.","details":[],"request_id":"req_generated","docs":""}}
```

| HTTP | Codes |
| --- | --- |
| 400 | BAD_REQUEST, malformed multipart |
| 401 | UNAUTHORIZED |
| 413 | PAYLOAD_TOO_LARGE, IMAGE_TOO_LARGE |
| 415 | UNSUPPORTED_MEDIA_TYPE |
| 422 | IMAGE_REQUIRED, INVALID_IMAGE |
| 429 | SERVICE_BUSY |
| 500 | INTERNAL_ERROR, invalid native output or inference exception |
| 503 | AUTH_NOT_CONFIGURED, MODEL_NOT_READY, OUTPUT_TOO_LARGE |
| 504 | REQUEST_TIMEOUT |

Generated request IDs appear in response headers and envelopes. Logs contain request ID, path, status, duration and failure category. Inputs, OCR text, credentials and exception messages are excluded. Inference runs in one executor thread. On HTTP deadline/disconnect, an ongoing native call retains the inference slot until it finishes. An indefinitely stuck native call requires a supervised process restart. Configure a proxy body/read deadline and operational restart policy.

## Multi-image Batch

`POST /api/v1/ocr-text-batches` accepts repeated multipart files named `images`. Authentication follows the single-image endpoint. The wrapper invokes `LineOCR.read(image)` sequentially on the existing reader. Batch and single requests share one admission slot, including multipart parsing. Concurrent POSTs receive429 with `Retry-After`5.

This example illustrates one success and one invalid image. Each submitted image retains its zero-based index. Successful `result` values use the single-image `data` schema and preserve full text, reading order, supplied geometry and nullable confidence.

```json
{"data":{"results":[{"index":0,"status":"success","result":{"text":"ตัวอย่าง","lines":[],"confidence":null,"geometry_available":false,"image":{"width":780,"height":250},"rotation":0,"text_angle":0},"error":null},{"index":1,"status":"error","result":null,"error":{"code":"INVALID_IMAGE","message":"The uploaded image is invalid."}}],"total":2,"succeeded":1,"failed":1},"meta":{"request_id":"req_generated","api_version":"v1","service":"openthai2-ocr-text","model":"iapp/OpenThai2.0-OCR-Text","model_revision":"39fa41bdd49f067ba41b1d9de79c06ab506d67d4","duration_ms":250}}
```

HTTP200 returns a complete ordered result list even when some or all images have per-image errors. Invalid/corrupt/empty/oversized images, excessive per-image output and native inference failures become error items. Native exception messages use a fixed safe replacement. Structural errors use the top-level error envelope and start no inference. Missing/wrong multipart fields return422 `IMAGES_REQUIRED`, malformed multipart400 `BAD_REQUEST`, unsupported media415, and excessive count or aggregate upload413. Unready/disabled service returns503.

Aggregate output overflow returns503 `OUTPUT_TOO_LARGE` for the whole request. A deadline returns504. A detected disconnect stops the remaining batch and emits a499 diagnostic when a response can still be sent. Clients may receive no response after disconnect. This stateless wrapper does not persist completed items. Retrying can repeat inference. OCRLab retains checkpoint-aware single mode until a Batch recovery contract is integrated.

| Environment variable | Default | Allowed range or behavior |
| --- | --- | --- |
| `OPENTHAI_MAX_BATCH_IMAGES` |8|1–16|
| `OPENTHAI_MAX_BATCH_UPLOAD_BYTES` |20MiB|1byte–80MiB, plus64KiB multipart body overhead|
| `OPENTHAI_MAX_UPLOAD_BYTES` |10MiB|Per-image ceiling shared with single mode|
| `OPENTHAI_MAX_PIXELS` |2,000,000|Per-image decoded pixel ceiling|
| `OPENTHAI_MAX_DIMENSION` |8000|Per-image dimension ceiling|
| `OPENTHAI_MAX_BATCH_RESPONSE_BYTES` |8MiB|1KiB–16MiB aggregate serialized response|
| `OPENTHAI_MAX_RESPONSE_BYTES` |2MiB|Per-image encoded item ceiling, shared setting with single response|
| `OPENTHAI_BATCH_TIMEOUT_SECONDS` |120|Greater than0, at most600seconds including upload|
| `OPENTHAI_MAX_CONCURRENT_BATCH_REQUESTS` |1|0disables Batch,1uses the shared native slot|

The parser spools files and closes them on success, error, timeout or disconnect. One raw image and one decoded image are processed at a time. Encoded result items accumulate within the aggregate response limit. A running native call retains its byte buffer after HTTP cancellation and closes its decoded image explicitly at completion. Native calls cannot be forcibly cancelled.

Single and Batch cleanup use Starlette's parser-owned temporary-handle list to cover failures before `FormData` exists. Retain the interrupted-upload regression tests when upgrading Starlette. They verify that disconnect, body-limit exceptions and cancellation close every partially created file, including uploads rolled to disk. A detected Single upload disconnect uses the499 diagnostic and existing safe error envelope. Successful Single response fields and model conversion are unchanged.
