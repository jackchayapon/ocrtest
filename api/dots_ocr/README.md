# Standalone Dots OCR API

FastAPI service independent of OCRLab. No database, external URL input, Pipeline registration, or OCRLab runtime dependency. All implementation, tests and evidence are in this directory.

Default model: `dots-studio/dots.ocr`, pinned revision `c0111ce6bc07803dbc267932ffef0ae3a51dc951`, Transformers/SDPA. Alternative tested Linux/CUDA profile: `dots-studio/dots.mocr` revision `7c53434cd403d2e7f5f1d745eb2a2467a6473423`, vLLM 0.17.1. These are separate runtime profiles; do not install arbitrary newer Transformers over the native requirements.

This is a review/handover implementation, **not a deployment or a production capacity guarantee**. See [measured results and limitations](docs/BENCHMARK_REPORT.md).

## Native setup (Python 3.12)

Run commands from `api/dots_ocr/`. Install into a new environment, not OCRLab's environment.

```sh
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv/Scripts/Activate.ps1
# For the tested NVIDIA profile, install matching CUDA wheels first:
python -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121
python -m pip install -r requirements-dev.txt
python scripts/download_models.py dots-studio/dots.ocr
```

The downloader requests public, exact-revision snapshots with `token=False`, verifies every file against the committed HF Git/LFS hashes, and retains upstream license files. Runtime verifies the snapshot again before executing pinned custom model code. Model weights/caches are never committed. Outbound network is unnecessary after download. Review the pinned upstream code and model agreements before redistribution.

Copy `.env.example` to local `.env` and configure a private random `DOTS_API_KEY` (for example generate it with Python `secrets.token_urlsafe(32)`). Never put credentials in Git or command-line flags. Native Windows CUDA is measured; CPU inference is **untested**, not an asserted minimum working configuration.

```sh
python -m app.main
```

Default port 8092. Use exactly one worker/process per model. Do not run `uvicorn --workers N`: admission is process-local and multiple models can exhaust GPU memory.

## API

```sh
curl http://127.0.0.1:8092/health
curl -H "Authorization: Bearer $DOTS_API_KEY" http://127.0.0.1:8092/api/v1/readiness
curl --fail-with-body -H "Authorization: Bearer $DOTS_API_KEY" \
  -F image=@tests/fixtures/english.png http://127.0.0.1:8092/api/v1/ocr-text
curl --fail-with-body -H "Authorization: Bearer $DOTS_API_KEY" \
  -F images=@tests/fixtures/english.png -F images=@tests/fixtures/thai.png \
  http://127.0.0.1:8092/api/v1/ocr-text-batches
```

PowerShell users should use `curl.exe` and `$env:DOTS_API_KEY`. Read [API_CONTRACT.md](docs/API_CONTRACT.md) before writing a client; this schema is not OpenThai's `lines` schema.

## Docker (build context is this directory only)

```sh
docker build -t dots-api:cpu .
# CPU image build/start/auth verified; CPU model inference remains unverified.
docker build -f Dockerfile.vllm -t dots-api:vllm .
# Export DOTS_API_KEY privately before running. Do not put its value in argv.
docker run --rm --gpus all --shm-size 256m -p 127.0.0.1:8092:8092 \
  -e DOTS_API_KEY -e DOTS_MODEL_ID=dots-studio/dots.mocr \
  -e VLLM_WORKER_MULTIPROC_METHOD=spawn \
  --mount type=bind,src=/absolute/path/models,dst=/service/models,readonly \
  dots-api:vllm
```

Download the selected snapshot first. GPU commands are **operator instructions, not a CDGS deployment performed by this task**. Default Docker is CPU; `Dockerfile.vllm` supplies the measured Linux/CUDA stack. Native CUDA wheels can also be selected with `--build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu121`, but that Docker variant was not benchmarked. Docker liveness does not imply model readiness. Supply TLS at a reverse proxy, keep the service on a private interface where possible, and check authenticated readiness before traffic. No provider or OCRLab configuration is changed.

## Verification

```sh
python -m pytest tests -q
python -m ruff check app tests scripts
python -m compileall -q app scripts
python scripts/benchmark.py --output benchmarks/private/my-run
python scripts/verify_responses.py benchmarks/private/my-run
```

Unit/contract tests use an explicitly identified test-double reader. The benchmark script never does; it starts the real model and real loopback HTTP. See [HANDOVER.md](docs/HANDOVER.md), [FEATURE_SUPPORT_MATRIX.md](docs/FEATURE_SUPPORT_MATRIX.md), and [REAL_RESPONSE_EXAMPLES.md](docs/REAL_RESPONSE_EXAMPLES.md). All included fixtures and OCR responses are synthetic.
