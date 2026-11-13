# CDGS standalone OpenThai handover

## 1. Source and release identity

Source is [api/openthai2_ocr_text](https://github.com/jackchayapon/ocrtest/tree/feature/openthai-api-batching/api/openthai2_ocr_text), reviewed through [PR18](https://github.com/jackchayapon/ocrtest/pull/18). Earlier Batch baseline was `a1b24d8feb58245330a280ff0ce11db6a6f525e3`. The final Thai handover message records exact reviewed feature and merged main SHAs. Pin that final SHA and verify it locally.

```sh
set -euo pipefail
git fetch origin main
: "${SOURCE_COMMIT:?Set the full verified SHA from the final handover message}"
# Preserve existing local secrets, snapshot and previous source/image first.
git switch --detach "$SOURCE_COMMIT"
test "$(git rev-parse HEAD)" = "$SOURCE_COMMIT"
cd api/openthai2_ocr_text
```

## 2. Deployment architecture

Update the **existing OpenThai service in place** from this independent directory on the same server infrastructure as CDGS Gateway. OCRLab can run elsewhere. Keep this FastAPI, ONNX Runtime, model, Dockerfile and configuration together. The other repository was inspected for compatibility context. Updating its source is unnecessary for this standalone deployment.

## 3. Verify existing service identity

The owner identifies the current supervisor, container, Compose project/service labels, private port, snapshot and private environment file. Commands below apply when the existing service matches the packaged name `openthai`. Reconcile another service name before running replacement commands. A non-Compose deployment uses its current supervisor's update procedure.

```sh
: "${EXISTING_COMPOSE_PROJECT:?Set the existing deployed Compose project name}"
: "${EXISTING_SERVICE:?Set the existing service name}"
: "${PRIVATE_ENV:?Set the existing private environment-file absolute path}"
test "$EXISTING_SERVICE" = openthai
chmod 600 "$PRIVATE_ENV"
dc() { docker compose --env-file "$PRIVATE_ENV" -p "$EXISTING_COMPOSE_PROJECT" -f "$PWD/compose.yaml" "$@"; }
dc config --quiet
CURRENT_ID="$(dc ps -q "$EXISTING_SERVICE")"
test -n "$CURRENT_ID"
test "$(printf '%s\n' "$CURRENT_ID" | wc -l)" -eq 1
test "$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$CURRENT_ID")" = "$EXISTING_COMPOSE_PROJECT"
```

An empty/multiple-container result stops this procedure. Reconcile the existing deployment before continuing. Review the packaged port/mount settings against the current configuration. Use `config --quiet` to avoid printing resolved secrets.

## 4. Build context and runtime

Build from this directory. Python3.12/Linux, ONNX Runtime CPU,1CPU,1536MiB/no swap in local tests,1worker,1executor and1shared native slot were verified. Docker runs UID10001, dropped capabilities, read-only root and32MiB `/tmp`. Extra workers each load a model and are disabled. Preserve the approved envelope and assess shared-host capacity with the owner.

## 5. Model snapshot

Use `iapp/OpenThai2.0-OCR-Text` revision `39fa41bdd49f067ba41b1d9de79c06ab506d67d4`, with its model card, NOTICE and license. Reuse the verified deployed snapshot when it matches. Otherwise provision before replacement.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/download_model.py
```

Startup checks every file against `model-manifest.json` before importing runtime. Compose mounts `./models/openthai2:/models/openthai2:ro`. Directories must be traversable and files readable by UID10001. Preserve the previous snapshot for rollback.

## 6. Environment variables

| Variable | Default or requirement |
| --- | --- |
| `OPENTHAI_API_KEY` | Required private printable-ASCII key without whitespace |
| `OPENTHAI_MODEL_DIR` | `/models/openthai2` in Docker |
| `OPENTHAI_PORT` |8091, private loopback binding |
| `OPENTHAI_THREADS`, `OPENTHAI_WORKERS` |1,1 |
| `OPENTHAI_MAX_UPLOAD_BYTES` |10485760 per image |
| `OPENTHAI_MAX_PIXELS`, `OPENTHAI_MAX_DIMENSION` |2000000,8000 |
| `OPENTHAI_MAX_RESPONSE_BYTES` |2097152 per image |
| `OPENTHAI_REQUEST_TIMEOUT_SECONDS` |120 |
| `OPENTHAI_MAX_BATCH_IMAGES` |8, configurable1–16 |
| `OPENTHAI_MAX_BATCH_UPLOAD_BYTES` |20971520 total image bytes |
| `OPENTHAI_MAX_BATCH_RESPONSE_BYTES` |8388608 aggregate bytes |
| `OPENTHAI_BATCH_TIMEOUT_SECONDS` |120 |
| `OPENTHAI_MAX_CONCURRENT_BATCH_REQUESTS` |1 shared slot,0disables Batch |

Compose explicitly forwards model directory/key and uses defaults for the rest. Put approved overrides in its existing environment mapping after review. `--env-file` supplies interpolation and does not automatically forward arbitrary variables. [Full bounds](API_CONTRACT.md).

## 7. Authentication matching

This wrapper reads `OPENTHAI_API_KEY` and accepts Bearer or X-API-Key with constant-time comparison. Gateway `MODEL_GATEWAY_API_KEY` and another leaf's `INTERNAL_API_TOKEN` have separate meanings. The owner may deliberately configure an approved shared value in `OPENTHAI_API_KEY`. Actual CDGS credential matching remains unverified.

Compose refuses empty/unset keys. Direct startup with missing, whitespace/control/non-ASCII key skips loading and returns503 `AUTH_NOT_CONFIGURED`. Public `/health` gives only liveness. Never print keys, include them in URLs/command arguments or expose8091 publicly. Preserve private upstream authentication, firewall and TLS boundaries.

## 8. Internal Single endpoint

`POST /api/v1/ocr-text` accepts multipart `image`. Valid PNG/JPEG requests retain `{data,meta}`, full text, lines/reading order, nullable line confidence, model polygons, image metadata and request ID. Aggregate confidence remains null. Admission is shared with Batch.

## 9. Internal Batch endpoint

`POST /api/v1/ocr-text-batches` accepts repeated multipart `images`. Default8/max16 are processed sequentially using the loaded reader. HTTP200 contains ordered `{index,status,result,error}` plus total/succeeded/failed and meta. Individual corrupt/oversized images or native failures become item errors. Request-wide failures use the existing safe error envelope. [Request/response examples](API_CONTRACT.md).

## 10. Intended public routes

| Public CDGS path | Standalone internal path | State |
| --- | --- | --- |
| `/paddle/api/v1/openthai-text` | `/api/v1/ocr-text` | Supplied URL, deployed mapping unverified |
| `/paddle/api/v1/openthai-text-batches` | `/api/v1/ocr-text-batches` | **NOT DEPLOYED / PENDING CDGS** |

Public origin is `https://websolution.cdgs.co.th`. Prior unauthenticated Single GET returned401. Authorized inference, actual revision and current proxy mapping remain unverified.

## 11. Proxy/Gateway mapping

The owner implements these explicit mappings in the existing proxy technology. Preserve the Single public URL. Forward multipart bytes, repeated fields, content types and request IDs intact. Both paths must use the same existing worker and slot. Configure upstream credentials separately from public-client credentials. Proxy/Gateway edits and restarts belong to the infrastructure owner.

## 12. Body, deadline and temporary storage

Default content totals20MiB plus64KiB multipart overhead. Align proxy ceilings with this and per-image10MiB/pixel limits. The120second service deadline includes upload. An owner-validated125second proxy read budget can accommodate it. Review the entire proxy chain. Preserve TLS and per-client rate/connection limits. The32MiB temporary mount must cover accepted spooled files and temporary work. Increasing upload limits requires storage review.

## 13. Build and replace the existing instance

During the approved window, drain incoming inference at the existing proxy. Account for active native calls and caller retries. Preserve old image/config/snapshot securely. Continue only after section3 identity checks pass.

```sh
OLD_IMAGE_ID="$(docker inspect --format '{{.Image}}' "$CURRENT_ID")"
ROLLBACK_IMAGE="openthai2-ocr-text:rollback-$(date -u +%Y%m%dT%H%M%SZ)"
docker image tag "$OLD_IMAGE_ID" "$ROLLBACK_IMAGE"
dc build "$EXISTING_SERVICE"
dc up -d --no-deps --force-recreate "$EXISTING_SERVICE"
NEW_ID="$(dc ps -q "$EXISTING_SERVICE")"
test -n "$NEW_ID"
test "$(printf '%s\n' "$NEW_ID" | wc -l)" -eq 1
dc ps "$EXISTING_SERVICE"
```

Verify one instance, private ports and model permissions before reopening traffic. These are owner-run CDGS commands.

## 14. Liveness and readiness

```sh
curl --fail --silent --show-error http://127.0.0.1:8091/health
# Mode0600 private curl config contains the approved authentication header.
curl --fail --silent --show-error --config /private/openthai-curl.conf http://127.0.0.1:8091/api/v1/readiness
```

Readiness must return200 after checksum-verified loading. Missing/wrong client keys return401 with valid server configuration. Missing server authentication returns503. Liveness alone does not prove inference readiness.

## 15. Small synthetic Single/Batch smoke

Supply the private service key to the smoke process through the owner's secret mechanism. Run from this source directory. This sends one Single and one Batch of two synthetic images and prints only status/count/request ID.

```sh
python - <<'PY'
import os
from pathlib import Path
import httpx
image = Path('tests/fixtures/synthetic-thai-english.png').read_bytes()
with httpx.Client(base_url='http://127.0.0.1:8091', headers={'X-API-Key':os.environ['OPENTHAI_API_KEY']}, timeout=125, follow_redirects=False, trust_env=False) as client:
    single = client.post('/api/v1/ocr-text', files={'image':('synthetic.png',image,'image/png')})
    single.raise_for_status()
    batch = client.post('/api/v1/ocr-text-batches', files=[('images',('synthetic.png',image,'image/png'))]*2)
    batch.raise_for_status()
    data = batch.json()['data']
    assert data['succeeded'] == 2 and data['failed'] == 0
    assert [item['index'] for item in data['results']] == [0,1]
    assert all(item['result'] == single.json()['data'] for item in data['results'])
    print({'single_http':single.status_code,'batch_http':batch.status_code,'count':data['total'],'request_id':batch.headers['x-request-id']})
PY
```

After approved routing, repeat this tiny synthetic check against both exact public paths in section10 using the approved Gateway-client credential/header. Avoid a guessed public readiness URL or production load test. Confirm returned model revision and deployed source SHA with the owner.

## 16. Failure handling and cancellation

Expect401 for bad client credentials,413 for count/body bounds,429 with `Retry-After:5` while busy,503 for unavailable/config/output limits and504 for deadline. Detected disconnect uses499 when a response is possible. Remaining images stop. Native work can continue and retains the slot until completion. A stuck call needs supervised recovery. Stateless retries can repeat inference. OCRLab retains Single durable Jobs and committed per-Field checkpoints.

## 17. Monitoring and local evidence

Log request ID, safe path/status, duration and item index/status without OCR text, filenames or credentials. Monitor RSS, memory.current/peak/stat/events, CPU, latency,429,503/504, disk and fd counts. Retain source/image and OOM evidence. Latest local validation has50 tests and24 real-model timed trials, kernelpeak577,847,296bytes under1536MiB/1CPU, zero OOM/max events, source9/9match and restart smoke pass. [Measurements and limits](BATCH_BENCHMARKS.md).

## 18. Rollback

Withdraw Batch routing and drain/account for running work. Restore the previous image, compatible Single routing/auth and verified snapshot using the same project/service. Keep the private environment. Use an image-only override outside Git selecting `$ROLLBACK_IMAGE` for `openthai`, then run the same Compose project with that override and `up -d --no-build --no-deps --force-recreate openthai`. Verify one instance, health, authorized readiness and Single smoke before traffic. Retried in-flight inference can repeat. This standalone service has no database migration.

## 19. Limits and responsibility

Synthetic results cover the measured envelope. Dense pages, sustained shared-host load, actual CDGS authentication/routing/model revision and public Batch capacity require owner validation. Native tensor batching, parallel speedup and512MB capacity are unclaimed. **Actual server release and HTTP verification remain PENDING CDGS DEPLOYMENT.**

## 20. Final owner checklist

- [ ] Confirm final source/image SHA and pinned snapshot.
- [ ] Confirm existing project/service identity, one instance, private ports, mounts and approved1536MiB/1CPU envelope.
- [ ] Match private client/upstream credentials deliberately and test missing/wrong-key behavior.
- [ ] Replace the existing service during the approved window and preserve rollback material.
- [ ] Check health, authorized readiness, Single, Batch and restart recovery.
- [ ] Verify both public mappings, TLS, body/deadline/rate controls.
- [ ] Confirm ordered text/geometry/confidence with synthetic input and inspect safe logs/memory/OOM evidence.
- [ ] Return deployed commit/image identity and successful HTTP/request-ID evidence before marking VERIFIED ON CDGS.
