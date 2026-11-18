"""Measure process-first load versus explicit cache-warm reload; no cache flush."""

import gc
import hashlib
import json
import sys
import time
from pathlib import Path

import psutil
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from app.config import Settings
    from app.inference import Inference

    settings = Settings(_env_file=None)
    measurements = []
    for phase in [
        "process_first_filesystem_cache_uncontrolled",
        "cache_warm_explicit_reload",
    ]:
        runtime = Inference(settings)
        started = time.monotonic()
        torch.cuda.reset_peak_memory_stats()
        runtime.initialize()
        measurements.append(
            {
                "phase": phase,
                "seconds": time.monotonic() - started,
                "rss_after_load_bytes": psutil.Process().memory_info().rss,
                "torch_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                "torch_peak_reserved_bytes": torch.cuda.max_memory_reserved(),
            }
        )
        runtime.close()
        runtime.executor.shutdown()
        del runtime
        gc.collect()
    report = {
        "status": "REAL_MODEL_LOAD_PASS",
        "measurements": measurements,
        "true_disk_cold": "NOT_MEASURED: shared host caches were not flushed",
        "revision": settings.revision,
        "app_source_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "app").glob("*.py")
        },
        "snapshot_disk_bytes": sum(
            p.stat().st_size for p in settings.model_dir.rglob("*") if p.is_file()
        ),
        "venv_disk_bytes": sum(
            p.stat().st_size for p in (ROOT / ".venv").rglob("*") if p.is_file()
        ),
        "venv_limitation": "Native venv reuses system-site-packages (CUDA torch); footprint excludes shared dependencies. Docker image size is the reproducible full installation footprint.",
    }
    (ROOT / "benchmarks" / "load-profile.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(measurements))


if __name__ == "__main__":
    main()
