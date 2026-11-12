# Local verification

```sh
pip install -r requirements-dev.txt
python scripts/download_model.py
python -m pytest tests -q
python -m ruff check app tests scripts
python -m app
```

In another terminal, set the same private test key when authentication is enabled and run actual HTTP inference.

```sh
python scripts/smoke_http.py --font /path/to/NotoSansThai-Regular.ttf
curl -F image=@sample.png http://127.0.0.1:8091/api/v1/ocr-text
```

Service unit/HTTP tests use explicit reader doubles to exercise validation, NumPy conversion, blank output, authentication, readiness failure, contention, deadlines and cleanup. `smoke_http.py` talks to the running service and its actual installed model. Keep these results separately identified in test reports.

For Linux resource evidence, run the Compose service and read `/sys/fs/cgroup/memory.current`, `memory.peak`, `memory.events` and `memory.stat` in its container. Record limits and input dimensions. An observed low smoke peak does not establish dense-page or prolonged concurrency capacity. Use the cross-application verification report in the OCRLab `docs` directory for the measured local integration run.
