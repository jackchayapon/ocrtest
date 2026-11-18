# API contract v1 / data schema 1.0

## Requests and authentication

| Route | Request | Authentication |
|---|---|---|
| GET `/health` | No payload | Public liveness only |
| GET `/api/v1/readiness` | No payload | Bearer key |
| POST `/api/v1/ocr-text` | Multipart, exactly one `image` file | Bearer key |
| POST `/api/v1/ocr-text-batches` | Multipart, repeated `images`, 1–8 files | Bearer key |

All non-health routes are fail-closed: missing server key 503, incorrect/missing client key 401. There is no browser login, URL fetch, arbitrary model name, reload route, custom prompt or remote code selection. Public docs/OpenAPI endpoints are disabled. A single server-side key protects this standalone service; it is unrelated to OCRLab's Shared Workspace policy.

PNG/JPEG/static WebP are decoded by Pillow into RGB. Actual content, not filename/MIME, determines decoding. PDF 415 (not rendered); corrupt bytes 422; animated images 415. No rotation, deskew, EXIF transpose or ROI-offset correction is applied. Dimensions refer to stored input-image pixels. Consumers displaying a crop on a larger page must add their own offset exactly once.

Default limits: 10MiB/file, 40MiB/batch file bytes, 4MP input, longest dimension8000, batch8, 64KiB multipart overhead allowance per request. Streaming byte counting also applies without Content-Length. One admitted POST (upload through response), no unbounded waiting queue; busy429 with `Retry-After:5`. Multipart files are closed on success/failure.

Model preprocessing uses multiples of28, minimum3136 pixels and maximum1,003,520 pixels; larger accepted inputs are resized by the model processor. This is a quality/resource setting, **not a claim of native 4MP inference**. No comparative accuracy guarantee for downsampled documents is made. Defaults are configurable via `DOTS_` fields in `app/config.py` and recorded in every benchmark.

## Successful Single

`{"data": OCRData, "meta": Metadata}`. `OCRData` contains:

- `schema_version:"1.0"`, `image:{width,height}`, `model_image:{width,height}`.
- `native_output`: exact generated string, including native assistant terminator when present.
- `elements`: original model sequence. Each element has `index`, `category`, nullable `text`, `native_bbox`, `bbox`, `geometry_status`, `confidence:null`.
- Native boxes are rectangles `[x1,y1,x2,y2]` in the resized model-image frame, **not four-point polygons**. Valid `bbox` scales x/y once to input pixels. No spatial sort, clipping, rotation, or fabricated geometry occurs.
- Shape, finite values, positive area and coordinate bounds are checked. Nonfinite/malformed rectangles fail502. Valid-shape but out-of-frame native boxes are retained as `native_bbox`; `bbox:null`, `geometry_status:"out_of_bounds"`. Missing boxes are `absent`. The real blank fixture motivated this guard; an erroneous model box is not made plausible by clipping.
- `text` joins existing non-null element text with newlines in model order. It is a derived convenience field, not a second model prediction. Native complete output remains untouched.
- `tables` lists indices of Table elements. Their native HTML remains in element text; formulas retain LaTeX. No fabricated table cells, chart values or confidence scores.
- `coordinate_frame:"input_image_pixels"`, `reading_order:"model_sequence"`, `confidence:null`.

The parser accepts only a JSON list (optionally an exact JSON fence), plus a trailing `<|endofassistant|>` observed with the pinned OCR checkpoint. It does not guess objects, join unrelated raw formats or silently salvage invalid/truncated JSON. Limits:1024 elements and262144 generated characters, with configurable encoded data budgets8MiB/Single and16MiB/Batch; envelope metadata adds small bounded overhead. `max_new_tokens`4096; reaching the cap without EOS fails502.

Metadata includes request_id, api_version, model ID, full revision, runtime backend/device/dtype and duration_ms. `X-Request-ID` is server-generated and agrees with the body. Responses are `no-store`; no filename or credential is returned.

## Batch

`data:{results:[...],count,succeeded,failed,execution:"sequential_wrapper"}`.

Each item: `{index,status:"success"|"error",result:OCRData|null,error:null|{code,message},duration_ms}`. Input order and zero-based indices are preserved. Successful `result` equals Single `data` for the same image/configuration; test evidence includes exact object comparisons for1/2/4/8. An error item is never a successful OCR result. `data.results` is not `data.elements` or `data.lines`.

Inference is **sequential wrapper batching**, not true batched GPU execution. Decode/model errors may produce HTTP200 mixed outcomes, so clients must check item status/counts. Request-wide limits/auth/deadline errors are top-level errors. On inference deadline the batch stops with504 and does not invent results for unfinished items. Submitted native work retains its slot until completion; clients must not retry429 in a tight loop.

## Failure and timeout semantics

Error envelope: `{"error":{"code":"INVALID_IMAGE","message":"The uploaded image cannot be decoded."},"meta":{"request_id":"...","api_version":"v1"}}`.

| HTTP | Typical codes/meaning |
|---|---|
|400/422|Malformed multipart/fields, invalid image|
|401|UNAUTHORIZED|
|413|PAYLOAD_TOO_LARGE / IMAGE_TOO_LARGE|
|415|Unsupported format / animated image|
|429|SERVICE_BUSY; Retry-After5|
|502|MODEL_OUTPUT_INVALID / OUTPUT_TRUNCATED / RESPONSE_TOO_LARGE / MODEL_INFERENCE_FAILED|
|503|AUTH_NOT_CONFIGURED / MODEL_NOT_READY / RESOURCE_EXHAUSTED|
|504|INFERENCE_TIMEOUT / REQUEST_TIMEOUT|

Defaults: inference120s, Single request130s, Batch request600s. HTTP deadlines are bounded. PyTorch stops cooperatively between generation steps; vLLM blocking work is shielded. Neither mechanism can safely preempt an arbitrary native kernel. After timeout/disconnect, no second model call is admitted while the original future remains active. A permanently stuck native runtime requires supervisor intervention; there is no exactly-once inference, persisted queue or durable recovery claim. Shutdown drains outstanding native work and closes the owned model/engine. Use an external supervisor with a deliberate termination grace period.

## Python client

```python
import os
from contextlib import ExitStack
import httpx

with ExitStack() as stack, httpx.Client(
    base_url="http://127.0.0.1:8092", timeout=630,
    headers={"Authorization": "Bearer " + os.environ["DOTS_API_KEY"]},
    follow_redirects=False, trust_env=False,
) as client:
    streams = [stack.enter_context(open(p, "rb")) for p in
               ["tests/fixtures/english.png", "tests/fixtures/thai.png"]]
    response = client.post("/api/v1/ocr-text-batches",
                           files=[("images", ("synthetic.png", f, "image/png")) for f in streams])
    response.raise_for_status()
    for item in response.json()["data"]["results"]:
        if item["status"] == "success":
            print(item["index"], item["result"]["text"])
        else:
            print(item["index"], item["error"]["code"])
```

Treat native HTML/Markdown/SVG as untrusted content: sanitize in a future renderer. This service returns JSON and does not render it or integrate it into OCRLab.

## Device profiles

Native uses DOTS_DEVICE auto/cpu/cuda[:index]; only CUDA device0 was measured. In the vLLM profile use DOTS_DEVICE=auto and select the physical GPU with CUDA_VISIBLE_DEVICES before process startup. That runtime uses its first visible GPU and chooses its own attention kernel; DOTS_ATTENTION applies to the native Transformers profile only. Other GPU indices/precisions are not independently benchmarked.
