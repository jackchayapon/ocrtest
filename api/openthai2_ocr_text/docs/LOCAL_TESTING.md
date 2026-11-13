# Local verification

The current suite has 50 model-doubled tests, compared with the preceding37. It covers the original single route and Batch ordering, partial failures, authentication, body/count/pixel/output limits, shared admission, deadlines, disconnects, cleanup and OpenAPI. New cases reproduced missing/unusable-key exposure and Single upload handle leaks before their fixes. Interrupted-upload coverage includes both endpoints and in-memory/disk-backed files. Positive-path fixtures supply an explicit synthetic key, while missing/wrong-key tests retain their independent assertions. Run all tests through the standalone environment.

```sh
pip install -r requirements-dev.txt
python scripts/download_model.py
python -m pytest tests -q
python -m ruff check app tests scripts
# Configure a private OPENTHAI_API_KEY before starting the real service.
python -m app
```

In another terminal, configure the same required private test key and run actual HTTP inference.

```sh
python scripts/smoke_http.py --font /path/to/NotoSansThai-Regular.ttf
curl --config /private/openthai-curl.conf -F image=@sample.png http://127.0.0.1:8091/api/v1/ocr-text
```

Service unit/HTTP tests use explicit reader doubles to exercise validation, NumPy conversion, blank output, authentication, readiness failure, contention, deadlines and cleanup. `smoke_http.py` talks to the running service and its actual installed model. Keep these results separately identified in test reports.

For Linux resource evidence, run the Compose service and read `/sys/fs/cgroup/memory.current`, `memory.peak`, `memory.events` and `memory.stat` in its container. Record limits and input dimensions. An observed low smoke peak does not establish dense-page or prolonged concurrency capacity. Use the cross-application verification report in the OCRLab `docs` directory for the measured local integration run.

## Real-model Batch benchmark

Start the standalone Compose service with the verified model snapshot and a private local key. Set `OPENTHAI_API_KEY` in the benchmark process to the same key. The packaged fixture contains synthetic Thai/English text. The runner also generates a blank JPEG, compares complete results with single requests, and exercises a corrupt-image partial failure.

```sh
python scripts/benchmark_batch.py --url http://127.0.0.1:8091 --rounds 3 --output /private/path/batch-benchmark.json
```

The runner restricts its target to loopback and rejects redirects. Collect container resource counters separately during the run. Cold/warm and accepted-limit measurements, Docker source verification and sampling limitations are recorded in [the measured report](BATCH_BENCHMARKS.md). Do not point the benchmark at the CDGS production Gateway.
