"""Real local model + real loopback HTTP only. Never substitutes a test double."""

import argparse
import csv
import datetime
import hashlib
import json
import platform
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Sampler:
    def __init__(self):
        self.samples = []
        self.gpu_samples = []
        self.stop = threading.Event()

    def run(self):
        process = psutil.Process()
        process.cpu_percent()
        while not self.stop.wait(0.05):
            self.samples.append(
                {
                    "t": time.monotonic(),
                    "rss": process.memory_info().rss,
                    "host_used": psutil.virtual_memory().used,
                    "cpu_percent": process.cpu_percent(),
                }
            )
            cgroup = Path("/sys/fs/cgroup")
            if (cgroup / "memory.peak").exists():
                self.cgroup = {
                    name: (cgroup / name).read_text()
                    for name in [
                        "memory.current",
                        "memory.peak",
                        "memory.events",
                        "memory.stat",
                        "memory.max",
                    ]
                }

    def gpu_run(self):
        try:
            self.gpu_process = subprocess.Popen(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used,utilization.gpu",
                    "--format=csv,noheader,nounits",
                    "-lms",
                    "200",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            for line in self.gpu_process.stdout:
                if self.stop.is_set():
                    break
                try:
                    used, utilization = map(float, line.split(","))
                    self.gpu_samples.append(
                        {
                            "t": time.monotonic(),
                            "device_used_mib": used,
                            "utilization_percent": utilization,
                        }
                    )
                except ValueError:
                    pass
        except FileNotFoundError:
            self.gpu_process = None

    def summary(self, start, end):
        samples = [s for s in self.samples if start <= s["t"] <= end]
        gpu = [s for s in self.gpu_samples if start <= s["t"] <= end]
        return {
            "sampled_process_peak_rss_bytes": max(
                (s["rss"] for s in samples), default=None
            ),
            "sampled_host_used_ram_peak_bytes": max(
                (s["host_used"] for s in samples), default=None
            ),
            "sampled_cpu_percent_peak": max(
                (s["cpu_percent"] for s in samples), default=None
            ),
            "sampled_device_used_vram_peak_mib": max(
                (s["device_used_mib"] for s in gpu), default=None
            ),
            "sampled_device_gpu_utilization_peak_percent": max(
                (s["utilization_percent"] for s in gpu), default=None
            ),
        }


def main():
    import torch
    import transformers
    import uvicorn
    from app.config import Settings
    from app.main import create_app

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="dots-studio/dots.ocr")
    parser.add_argument(
        "--backend", choices=["transformers", "vllm"], default="transformers"
    )
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    key = secrets.token_urlsafe(32)
    settings = Settings(
        _env_file=None,
        api_key=key,
        model_id=args.model,
        backend=args.backend,
        device=args.device,
    )
    sampler = Sampler()
    threading.Thread(target=sampler.run, daemon=True).start()
    threading.Thread(target=sampler.gpu_run, daemon=True).start()
    app = create_app(settings)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
            ws="none",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    start = time.monotonic()
    thread.start()
    records = []
    report = {
        "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "evidence_type": "REAL_MODEL_REAL_HTTP",
        "model": args.model,
        "revision": settings.revision,
        "machine": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "cpu_logical": psutil.cpu_count(),
            "ram_total_bytes": psutil.virtual_memory().total,
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "transformers": transformers.__version__,
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        },
        "settings": settings.model_dump(mode="json", exclude={"api_key", "model_root"}),
        "measurement_limits": [
            "Shared workstation; other processes contribute to host/device totals.",
            "RSS/CPU sampled 50ms; total GPU sampled 200ms; sub-sample peaks may be missed.",
            "Process CPU percent may exceed100 on multicore; native model is one worker.",
            "First load is process-cold with filesystem cache uncontrolled; no cache flush.",
        ],
    }
    source_files = sorted((ROOT / "app").glob("*.py")) + [
        ROOT / "model-manifest.json",
        ROOT / "requirements.txt",
        Path(__file__).resolve(),
    ]
    report["source_sha256"] = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in source_files
    }
    if args.backend == "vllm":
        report["measurement_limits"].append(
            "Torch allocator and RSS metrics describe the API parent; vLLM inference runs in a child. Use cgroup and full-device measurements for that profile."
        )

    def persist():
        report["requests"] = records
        (args.output / "results.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    try:
        for _ in range(6000):
            if server.started:
                break
            time.sleep(0.1)
        report["startup_seconds"] = time.monotonic() - start
        report["startup_resources"] = sampler.summary(start, time.monotonic())
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}",
            timeout=settings.batch_timeout_seconds + 30,
            headers={"Authorization": "Bearer " + key},
            trust_env=False,
            follow_redirects=False,
        ) as client:
            ready = client.get("/api/v1/readiness")
            report["readiness"] = {"status": ready.status_code, "body": ready.json()}
            if ready.status_code != 200:
                report["status"] = "BLOCKED"
                report["load_error_category"] = getattr(
                    app.state, "load_error_type", "unknown"
                )
                persist()
                return
            fixtures = ROOT / "tests" / "fixtures"
            manifest = json.loads(
                (fixtures / "manifest.json").read_text(encoding="utf-8")
            )

            def request(label, names, batch=False):
                field = "images" if batch else "image"
                files = []
                for name in names:
                    path = fixtures / name
                    files.append(
                        (
                            field,
                            (path.name, path.read_bytes(), "application/octet-stream"),
                        )
                    )
                if torch.cuda.is_available():
                    torch.cuda.reset_peak_memory_stats()
                t = time.monotonic()
                response = client.post(
                    "/api/v1/ocr-text-batches" if batch else "/api/v1/ocr-text",
                    files=files,
                )
                end = time.monotonic()
                body = response.json()
                record = {
                    "label": label,
                    "images": names,
                    "batch_count": len(names),
                    "http_status": response.status_code,
                    "latency_seconds": end - t,
                    "response_bytes": len(response.content),
                    "input_sha256": [
                        hashlib.sha256(content[1][1]).hexdigest() for content in files
                    ],
                    **sampler.summary(t, end),
                    "torch_peak_allocated_bytes": torch.cuda.max_memory_allocated()
                    if torch.cuda.is_available()
                    else None,
                    "torch_peak_reserved_bytes": torch.cuda.max_memory_reserved()
                    if torch.cuda.is_available()
                    else None,
                    "response_file": f"response-{label}.json",
                }
                (args.output / record["response_file"]).write_text(
                    json.dumps(body, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                if batch and response.status_code == 200:
                    data = body["data"]
                    record.update(
                        succeeded=data["succeeded"],
                        failed=data["failed"],
                        indices=[r["index"] for r in data["results"]],
                    )
                elif response.status_code == 200:
                    data = body["data"]
                    record.update(
                        text=data["text"],
                        elements=len(data["elements"]),
                        tables=len(data["tables"]),
                        image=data["image"],
                        model_image=data["model_image"],
                    )
                else:
                    record["error_code"] = body.get("error", {}).get("code")
                records.append(record)
                persist()
                print(
                    json.dumps(
                        {
                            "label": label,
                            "status": response.status_code,
                            "seconds": end - t,
                        }
                    ),
                    flush=True,
                )
                return body

            for fixture in manifest:
                request(fixture["name"], [fixture["file"]])
            for resolution in [
                "resolution_small",
                "resolution_medium",
                "resolution_large",
            ]:
                for repeat in range(3):
                    request(f"{resolution}-repeat{repeat + 1}", [resolution + ".png"])
            for count in [1, 2, 4, 8]:
                names = [
                    "english.png",
                    "thai.png",
                    "mixed.png",
                    "crop.png",
                    "english.png",
                    "thai.png",
                    "mixed.png",
                    "crop.png",
                ][:count]
                body = request(f"batch{count}", names, True)
                if "data" in body:
                    expected = [
                        json.loads(
                            (args.output / f"response-{Path(n).stem}.json").read_text(
                                encoding="utf-8"
                            )
                        )["data"]
                        for n in names
                    ]
                    records[-1]["exact_single_equivalence"] = [
                        r["result"] for r in body["data"]["results"]
                    ] == expected
            request(
                "batch-mixed-error", ["english.png", "corrupt.png", "thai.png"], True
            )
            # Real model timeout test: keep worker busy until native work finishes.
            original_timeout = settings.inference_timeout_seconds
            settings.inference_timeout_seconds = 0.001
            request("real-deadline", ["english.png"])
            busy = client.post(
                "/api/v1/ocr-text",
                files={"image": ("busy.png", (fixtures / "english.png").read_bytes())},
            )
            report["deadline_busy_status"] = busy.status_code
            settings.inference_timeout_seconds = original_timeout
            pending = app.state.inference.pending
            while pending is not None and not pending.done():
                time.sleep(0.05)
            request("recovery-after-timeout", ["english.png"])
            report["status"] = "EXECUTED_REVIEW_PER_CASE"
            persist()
    finally:
        server.should_exit = True
        thread.join(settings.inference_timeout_seconds + 30)
        sampler.stop.set()
        process = getattr(sampler, "gpu_process", None)
        if process and process.poll() is None:
            process.terminate()
        report["overall_resources"] = sampler.summary(start, time.monotonic())
        report["cgroup_last_sample"] = getattr(sampler, "cgroup", None)
        report["server_stopped"] = not thread.is_alive()
        persist()
        if records:
            columns = [
                "label",
                "batch_count",
                "http_status",
                "latency_seconds",
                "response_bytes",
                "sampled_process_peak_rss_bytes",
                "sampled_cpu_percent_peak",
                "sampled_device_used_vram_peak_mib",
                "torch_peak_allocated_bytes",
                "torch_peak_reserved_bytes",
            ]
            with (args.output / "results.csv").open(
                "w", encoding="utf-8", newline=""
            ) as target:
                writer = csv.DictWriter(
                    target, fieldnames=columns, extrasaction="ignore"
                )
                writer.writeheader()
                writer.writerows(records)


if __name__ == "__main__":
    main()
