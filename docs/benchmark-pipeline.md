# Benchmark: DET V6 → baseline REC V5

Pipeline ID `benchmark`, display name `Benchmark`. Baseline DET V6 / REC V5 remains unchanged alongside Mint, Hutch Crop, Hutch Full and the separate [Thai FT v2](thai-ft-v2.md) adapter. Benchmark never sends a model variant or engine query.

## Verified Gateway contract (2026-09-21)

Authenticated probes used the synthetic `frontend/public/sample-document.png`, through the existing server-side Gateway configuration. `/api/v1/services` advertises **text-recognition-batches**, singular recognition. The plural `text-recognitions-batches` returns 404. OpenAPI/docs routes were unavailable, so real successful responses and read-only reference source were inspected.

Detection request:

```http
POST /api/v1/text-detection-batches?version=6
Authorization: Bearer <server-side key>
X-Request-ID: <run-id>_det
Content-Type: multipart/form-data; boundary=...

images: <canonical ROI PNG file>
```

One `images` file part is sent by this adapter. Repeated multipart `images` parts are the batch format (not a JSON string inside multipart). Detection returns `data.contract_version="leaf-inference-v1"`, `data.kind="text_detection_batch"`, `data.count=1`, and `data.result.results[0]` with `dt_polys` and parallel `dt_scores`. Observed polygons are four `[x,y]` pixel points in top-left, top-right, bottom-right, bottom-left order, relative to the submitted crop. `data.model_selection` identified `PP-OCRv6_medium_det`, baseline v6. Additional aliases/raw output are retained only after existing redaction.

Recognition request:

```http
POST /api/v1/text-recognition-batches?version=5
Authorization: Bearer <server-side key>
X-Request-ID: <run-id>_rec_<batch-index>
Content-Type: multipart/form-data; boundary=...

images: <line-0 PNG file>
images: <line-1 PNG file>
...
```

No `model`, `engine`, or fine-tune parameter is sent. `data.results[]` contains one item per image, with `text`, `confidence`, `segments`, `raw_segments`, `predictions`, `preprocessing="recognition_only"`, and `model="th_PP-OCRv5_mobile_rec"`; `data.count` equals the number of images. Three distinct crops (Thai heading, OCR LAB, OCR-DEMO-001) were sent forward and reversed: results followed the submitted order in both real calls. There is no explicit per-item correlation ID: pairing relies on this verified ordering and exact count validation, not filenames or sorting.

Both envelopes have `meta.request_id`, `api_version`, `service`, `model`, and `duration_ms`. Sanitized synthetic fixtures are in `backend/tests/fixtures/benchmark-{detection-v6,recognition-v5}.json`.

## Composition and persistence

The newer verified recognition leaf envelope has `contract_version=leaf-inference-v1`, `kind=text_recognition_batch`, and `data.results[*].rec_text/rec_score`. The adapter also supports the earlier `text/confidence` shape. Exact result counts and input ordering are required in both; raw envelopes remain unchanged apart from security redaction.

- TestCaseService prepares the same canonical PNG for Mint, Hutch Crop and Benchmark. Hutch Full uses the complete selected image/PDF page for Auto ROI or no ROI; for explicit Manual ROI it creates the canonical crop inside its adapter. Benchmark DET/REC requests are unchanged; see [Field GT and ROI rules](fields-roi-dataset.md).
- Benchmark keeps DET's output order (which is not necessarily reading order). It rectifies each quadrilateral using OpenCV perspective transform, cubic interpolation and replicated borders, then encodes a lossless PNG in memory. Width/height are rounded maximum opposing-edge lengths; no orientation classification or text correction is added.
- REC requests contain at most eight line crops per request. This is an application batching choice, not a claim about the Gateway maximum. Empty detections return empty text without a REC call. Invalid geometry, count mismatches or malformed text fail the run rather than silently pairing text with the wrong region. At most 1,000 regions are accepted to bound work.
- Texts are joined with LF in detection order. Raw/final text are identical at this stage. Existing PipelineManager normalization, metrics and error-event processing are reused unchanged. Confidence is the mean of available valid REC confidence values; missing confidence remains null.
- Existing geometry normalization supplies crop-relative and document-relative boxes (offset by the final ROI). `crop_sha256` records the input to DET, not the individual line crops.
- `raw_response.detection` and `raw_response.recognition_batches` preserve each stage's sanitized envelope and metadata. Image payloads, credentials and data URLs are redacted by the existing Gateway client. No temporary crop files are written.
- `processing_time_ms` is total adapter wall time; `gateway_duration_ms` is the sum of stage timings when every timing is present, otherwise null. The top-level Gateway request ID references DET; individual REC request IDs remain in `raw_response`.

## Configuration and rollout

The existing idempotent startup seed inserts only a missing `benchmark` config, enabled by default. It never updates existing pipeline settings. No schema migration or new environment variables are required. Existing `MODEL_GATEWAY_BASE_URL`, `MODEL_GATEWAY_API_KEY`, timeout and response-size limits apply. Detection/recognition routes and versions are adapter invariants; settings allow display name/enabled changes but reject incompatible Benchmark protocol changes.

The current Gateway readiness response lists integrated services but does not independently report the DET/REC leaves. Benchmark's Test Connection therefore reports `unknown`, not an invented healthy status; a successful OCR run is the definitive integration check.

This change does not deploy itself. Validate using an isolated local PostgreSQL test database, never production Neon. Existing historical records, Dataset export and CER/WER semantics are unchanged.
