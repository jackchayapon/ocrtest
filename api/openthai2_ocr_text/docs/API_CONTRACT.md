# HTTP contract v1

`GET /health` returns HTTP200 `{"status":"alive"}` without inference. `GET /api/v1/readiness` returns HTTP200 with `status=ready` after successful loading, or HTTP503 `MODEL_NOT_READY`. Readiness and inference require the configured API key. Model loading failures leave liveness operational for diagnosis.

`POST /api/v1/ocr-text` accepts exactly one multipart file named `image`. PNG and JPEG content are accepted regardless of filename. Default upload limit is 10 MiB, request body limit is upload limit plus64 KiB, pixel limit2,000,000 and maximum dimension8000. The request deadline defaults120 seconds. These service limits are operator-configurable. One request is admitted before multipart parsing and inference. Other POSTs receive429 with `Retry-After: 5`.

Success has the following shape. Values below illustrate the contract.

```json
{"data":{"text":"ข้อความ","lines":[{"text":"ข้อความ","confidence":0.98,"row":0,"box":[[1,2],[80,2],[80,30],[1,30]]}],"confidence":null,"geometry_available":true,"image":{"width":300,"height":200},"rotation":0,"text_angle":0},"meta":{"request_id":"req_generated","api_version":"v1","service":"openthai2-ocr-text","model":"iapp/OpenThai2.0-OCR-Text","model_revision":"39fa41bdd49f067ba41b1d9de79c06ab506d67d4","duration_ms":120}}
```

Full text follows model reading order. Polygon coordinates use original input pixels, after the runtime's inverse rotation/deskew. Confidence is nullable per line and always null at aggregate level. Empty inference returns empty text and lines with `geometry_available=false`. The API bounds lines1024, text32768 characters and serialized response2 MiB by default.

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
| 503 | MODEL_NOT_READY, OUTPUT_TOO_LARGE |
| 504 | REQUEST_TIMEOUT |

Generated request IDs appear in response headers and envelopes. Logs contain request ID, path, status, duration and failure category. Inputs, OCR text, credentials and exception messages are excluded. Inference runs in one executor thread. On HTTP deadline/disconnect, an ongoing native call retains the inference slot until it finishes. An indefinitely stuck native call requires a supervised process restart. Configure a proxy body/read deadline and operational restart policy.
