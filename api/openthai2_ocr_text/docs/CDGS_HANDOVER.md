# CDGS OpenThai Batch handover

The team supplied the single-image URL `https://websolution.cdgs.co.th/paddle/api/v1/openthai-text`. An unauthenticated live GET returned HTTP 401. The reference repository at commit `42818f8220eedebcd63fb9f71631a0707c89c1e9` declares POST, multipart field `image`, PNG/JPEG and a `{data, meta}` response. Its leaf uses `INTERNAL_API_TOKEN`, and its README names `MODEL_GATEWAY_API_KEY` for Gateway clients. The deployed authentication arrangement and actual OCR response require an approved credential and a successful synthetic POST. Source inspection and HTTP 401 do not verify model availability. [Reference service](https://github.com/ThanaphatP-lab/API_Service/blob/42818f8220eedebcd63fb9f71631a0707c89c1e9/services/ocr_openthai/main.py), [reference authentication guidance](https://github.com/ThanaphatP-lab/API_Service/blob/42818f8220eedebcd63fb9f71631a0707c89c1e9/services/ocr_openthai/README.md).

## Owner actions and routing

The proposed public Batch URL is `https://websolution.cdgs.co.th/paddle/api/v1/openthai-text-batches`. It has not been deployed or verified. Preserve the existing single-image public URL during any future upgrade.

| Public resource | Standalone wrapper internal route | Verification state |
| --- | --- | --- |
| `/paddle/api/v1/openthai-text` | `/api/v1/ocr-text` when the owner chooses this wrapper | Existing supplied public URL, deployed mapping unverified |
| `/paddle/api/v1/openthai-text-batches` | `/api/v1/ocr-text-batches` | Proposed mapping requiring owner approval and deployment |

The reference CDGS leaf declares its own `/paddle/api/v1/openthai-text` route. This wrapper uses the internal routes in the table. Apply the appropriate explicit rewrite during integration. Avoid repeated prefixes and appended guessed suffixes. Route single and Batch to the same worker/model instance to enforce their shared slot. If porting Batch into the reference service, preserve that service's shared authentication and request controls.

Gateway/Nginx must accept repeated multipart `images` fields, forward binary bodies and content types intact, enforce the approved upload ceiling plus multipart overhead, reject unexpected redirects, preserve request IDs, and allow the approved Batch deadline. Keep existing TLS and client authentication. Configure the upstream credential privately to match `OPENTHAI_API_KEY`. Confirm whether public client and internal service tokens differ. Avoid token literals in committed proxy configuration or forwarding a client token to an unapproved origin.

For the default 20 MiB content ceiling, allow at most 20 MiB plus 64 KiB of multipart body and align proxy settings. A 125-second proxy read budget can cover the default 120-second service deadline. Validate the owner's actual proxy chain before applying these values. Gateway and Nginx changes remain owner operations.

## Build, configuration and rollout

Build from this directory with `docker build -t openthai2-ocr-text:batch .`. Provision the pinned snapshot and mount it read-only at `/models/openthai2`. Set `OPENTHAI_MODEL_DIR`, `OPENTHAI_API_KEY` through a private secret, `OPENTHAI_THREADS=1` and `OPENTHAI_WORKERS=1`. The standalone wrapper reads `OPENTHAI_API_KEY`. The reference leaf reads `INTERNAL_API_TOKEN`. Align authentication deliberately.

Batch defaults are eight images, 20 MiB total content, 10 MiB per image, 2 MP per image, 8 MiB aggregate output and 120 seconds. `OPENTHAI_MAX_CONCURRENT_BATCH_REQUESTS=1` shares admission with single requests, and zero disables Batch. Full variable names/ranges are in [the API contract](API_CONTRACT.md). Ensure temporary storage covers the selected upload limit. The existing Compose profile provides 32 MiB of `/tmp`, sufficient for the default synthetic checks and requiring review when limits increase.

Local validation includes 37 model-doubled tests, actual HTTP Batch inference for 1/2/4/8 images, partial failures, cold/warm runs and a 2 MP by eight case. The tested standalone limit was 1,536 MiB with one CPU. Final-source kernel peak was 352,837,632 bytes, with an earlier run reaching 573,382,656 bytes. Host cache reuse affects these totals. Measure the owner's dense-page workload, allocation and queue behavior before selecting production limits. [Local measurements](BATCH_BENCHMARKS.md).

Smoke the original single endpoint before exposing Batch. Check missing/wrong-key errors, valid PNG/JPEG, ordered mixed success/failure, 429 admission and `Retry-After`, timeout/disconnect recovery, output limits and secret-safe logs. Verify that an ongoing native call retains its slot after HTTP cancellation. A permanently stuck native call requires owner-supervised restart.

For rollback, first disable or withdraw the new Batch route, drain or account for active native work, then restore the prior service image and compatible routing/authentication. Preserve the snapshot and secrets. Retrying interrupted stateless requests may repeat inference. OCRLab continues using single-image durable Jobs and checkpoints.

## Delivery status

Standalone Batch code is implemented and tested locally. OCRLab production recovery is deployed separately. The shared OpenThai configuration is prepared in disabled state without copying a server-managed credential. Live single-image authentication/inference awaits the approved key. CDGS Batch deployment and public activation remain infrastructure-owner actions. A handover recipient/channel has not been supplied, so this document is prepared for forwarding through the review PR.
