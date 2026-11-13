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
python -m app
```

The default model directory is `models/openthai2`. Set `OPENTHAI_MODEL_DIR` for a mounted snapshot. Provisioning downloads approximately 4.24 MB of runtime, ONNX weights, configuration and notices from a pinned public revision. Startup verifies every file against `model-manifest.json` before importing the runtime. Keep the downloaded NOTICE and model card alongside the weights.

```sh
curl http://127.0.0.1:8091/health
curl http://127.0.0.1:8091/api/v1/readiness
curl -F image=@sample.png http://127.0.0.1:8091/api/v1/ocr-text
python scripts/smoke_http.py --font /path/to/NotoSansThai-Regular.ttf
curl -F images=@sample1.png -F images=@sample2.jpg http://127.0.0.1:8091/api/v1/ocr-text-batches
```

When `OPENTHAI_API_KEY` is configured, readiness and inference accept `Authorization: Bearer …` or `X-API-Key`. Supply secrets through the deployment environment. Liveness stays lightweight and public.

| Guide | Content |
| --- | --- |
| [API contract](docs/API_CONTRACT.md) | Multipart input, response, error codes and limits |
| [Model I/O](docs/MODEL_IO.md) | Verified runtime revision, coordinates, confidence and license |
| [Deployment](docs/DEPLOYMENT.md) | Container, proxy, resources and operations |
| [Local testing](docs/LOCAL_TESTING.md) | Unit tests, actual HTTP and inference reproduction |

API-level Batch accepts up to 8 images by default and reads them sequentially through the existing model and admission slot shared with single-image requests. The configurable count has an upper bound of 16. Uploads are bounded and spooled, images decode one at a time, and results retain input indices with per-image errors. Deadlines/disconnects stop remaining work while a running native operation keeps its slot. Inference uses one executor thread.

OCRLab uses a Public Shared Workspace with editable External Provider configuration and write-only encrypted keys. It submits single-image requests through durable Jobs and per-Field checkpoints. The supplied CDGS single-image target is `https://websolution.cdgs.co.th/paddle/api/v1/openthai-text`. Its authentication and deployed behavior require separate live verification. The proposed public Batch path requires CDGS routing and deployment approval. The repository Batch route is ready for local testing and handover.

See [Batch measurements](docs/BATCH_BENCHMARKS.md) and [CDGS handover](docs/CDGS_HANDOVER.md).
