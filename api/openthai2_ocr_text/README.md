# OpenThai 2.0 OCR Text API

Standalone CPU inference service. Build context, tests, model provisioning and deployment live in this directory. Run every command below from `api/openthai2_ocr_text`.

```sh
python -m venv .venv
# Linux
. .venv/bin/activate
# Windows PowerShell alternative
# .venv/Scripts/Activate.ps1
pip install -r requirements-dev.txt
python scripts/download_model.py
python -m pytest tests -q
# Configure OPENTHAI_API_KEY through your private environment before startup.
python -m app
```

The default model directory is `models/openthai2`. Set `OPENTHAI_MODEL_DIR` for a mounted snapshot. Provisioning downloads approximately 4.24 MB of runtime, ONNX weights, configuration and notices from a pinned public revision. Startup verifies every file against `model-manifest.json` before importing the runtime. Keep the downloaded NOTICE and model card alongside the weights.

```sh
curl http://127.0.0.1:8091/health
# Use a mode-0600 curl config containing the private authentication header.
curl --config /private/openthai-curl.conf http://127.0.0.1:8091/api/v1/readiness
curl --config /private/openthai-curl.conf -F image=@sample.png http://127.0.0.1:8091/api/v1/ocr-text
python scripts/smoke_http.py --font /path/to/NotoSansThai-Regular.ttf
curl --config /private/openthai-curl.conf -F images=@sample1.png -F images=@sample2.jpg http://127.0.0.1:8091/api/v1/ocr-text-batches
```

`OPENTHAI_API_KEY` is required for readiness and inference. It must be nonempty printable ASCII without whitespace. Missing or unusable configuration leaves `/health` public, skips model loading and returns503 `AUTH_NOT_CONFIGURED` from protected APIs. Compose refuses an unset/empty key before creating a container. Valid configuration accepts `Authorization: Bearer …` or `X-API-Key`, using constant-time comparison. Supply secrets through the private deployment environment.

| Guide | Content |
| --- | --- |
| [API contract](docs/API_CONTRACT.md) | Multipart input, response, error codes and limits |
| [Model I/O](docs/MODEL_IO.md) | Verified runtime revision, coordinates, confidence and license |
| [Deployment](docs/DEPLOYMENT.md) | Container, proxy, resources and operations |
| [Local testing](docs/LOCAL_TESTING.md) | Unit tests, actual HTTP and inference reproduction |

API-level Batch accepts up to 8 images by default and reads them sequentially through the existing model and admission slot shared with single-image requests. The configurable count has an upper bound of 16. Uploads are bounded and spooled, images decode one at a time, and results retain input indices with per-image errors. Deadlines/disconnects stop remaining work while a running native operation keeps its slot. Inference uses one executor thread.

OCRLab uses a Public Shared Workspace with editable External Provider configuration and write-only encrypted keys. It submits single-image requests through durable Jobs and per-Field checkpoints. The supplied CDGS single-image target is `https://websolution.cdgs.co.th/paddle/api/v1/openthai-text`. Its authentication and deployed behavior require separate live verification. The proposed public Batch path requires CDGS routing and deployment approval. The repository Batch route is ready for local testing and handover.

See [Batch measurements](docs/BATCH_BENCHMARKS.md) and [CDGS handover](docs/CDGS_HANDOVER.md).

The infrastructure team updates its existing OpenThai service from this standalone directory on the same server infrastructure as CDGS Gateway. Reuse its existing project/service identity and supervisor after verifying them.
