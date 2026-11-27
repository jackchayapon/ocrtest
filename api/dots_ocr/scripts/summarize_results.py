"""Build presentation-ready evidence from completed real runs only."""

import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    benchmarks = ROOT / "benchmarks"
    hardware = json.loads(
        (benchmarks / "hardware.json").read_text(encoding="utf-8-sig")
    )
    fixtures = json.loads(
        (ROOT / "tests/fixtures/manifest.json").read_text(encoding="utf-8")
    )
    profiles = []
    rows = []
    capabilities = []
    for label in ["ocr-final", "mocr-vllm-final"]:
        directory = benchmarks / label
        report = json.loads((directory / "results.json").read_text(encoding="utf-8"))
        assert (
            report["status"] == "EXECUTED_REVIEW_PER_CASE" and report["server_stopped"]
        )
        verification = json.loads((directory / "verification.json").read_text())
        assert verification["status"] == "PASS"
        source_hashes = report.get(
            "source_canonical_lf_sha256", report["source_sha256"]
        )
        mismatches = [
            name
            for name, value in source_hashes.items()
            if hashlib.sha256(
                (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest()
            != value
        ]
        assert not mismatches, mismatches
        profile = {
            "profile": label,
            "model": report["model"],
            "revision": report["revision"],
            "machine": report["machine"],
            "load_seconds": report["readiness"]["body"]["load_seconds"],
            "resources": report["overall_resources"],
            "cgroup": report.get("cgroup_last_sample"),
            "requests": len(report["requests"]),
            "verification": verification,
            "resolution_latency": [],
            "batch_latency": [],
            "source_hashes_match": True,
        }
        for resolution in ["resolution_small", "resolution_medium", "resolution_large"]:
            times = sorted(
                r["latency_seconds"]
                for r in report["requests"]
                if r["label"].startswith(resolution + "-repeat")
            )
            assert len(times) == 3
            profile["resolution_latency"].append(
                {
                    "fixture": resolution,
                    "n": len(times),
                    "p50_seconds": statistics.median(times),
                    "p95_nearest_rank_seconds": times[math.ceil(0.95 * len(times)) - 1],
                }
            )
        for count in [1, 2, 4, 8]:
            record = next(
                r for r in report["requests"] if r["label"] == f"batch{count}"
            )
            profile["batch_latency"].append(
                {
                    "images": count,
                    "latency_seconds": record["latency_seconds"],
                    "images_per_second": count / record["latency_seconds"],
                    "single_equivalence": record["exact_single_equivalence"],
                }
            )
        profiles.append(profile)
        for record in report["requests"]:
            rows.append({"profile": label, **record})
        for fixture in fixtures:
            record = next(
                r for r in report["requests"] if r["label"] == fixture["name"]
            )
            response = json.loads(
                (directory / record["response_file"]).read_text(encoding="utf-8")
            )
            data = response.get("data")
            capabilities.append(
                {
                    "profile": label,
                    "fixture": fixture["name"],
                    "category": fixture["category"],
                    "http_status": record["http_status"],
                    "expected_marker_found": fixture.get("expected_text", "")
                    in data["text"]
                    if data
                    else None,
                    "geometry_out_of_bounds": sum(
                        e["geometry_status"] == "out_of_bounds"
                        for e in data["elements"]
                    )
                    if data
                    else None,
                    "categories": [e["category"] for e in data["elements"]]
                    if data
                    else [],
                    "evidence": f"{label}/{record['response_file']}",
                }
            )
    summary = {
        "evidence_type": "MEASURED_LOCAL_SYNTHETIC",
        "hardware": hardware,
        "profiles": profiles,
        "capabilities": capabilities,
        "methodology": {
            "rss_cpu_sampling_ms": 50,
            "device_gpu_sampling_ms": 200,
            "percentile": "nearest rank, n3 per resolution; descriptive small sample, not capacity",
            "throughput": "images / completed sequential Batch HTTP wall time",
            "accuracy": "limited expected-marker checks; no general OCR quality/CER claim",
            "shared_host": True,
        },
        "blocked_or_untested": [
            "Native MOCR/Transformers4.51.3 processor compatibility",
            "CPU model inference",
            "true cache-flushed disk-cold loading",
            "sustained dedicated-host capacity",
            "hard native kernel hang",
            "target CDGS server deployment",
        ],
        "observed_issues": [
            "Blank images can produce out-of-frame Picture boxes; retained native, mapped box null with out_of_bounds",
            "vLLM6GiB reaches memory.max with file-cache pressure; no OOM observed",
            "vLLM child emits NCCL teardown warning at exit; no leftover benchmark container",
        ],
        "not_performed": [
            "OCRLab integration",
            "Production data access",
            "CDGS changes",
            "Railway/Vercel deployment",
            "slides",
        ],
    }
    (benchmarks / "results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    columns = [
        "profile",
        "label",
        "batch_count",
        "http_status",
        "latency_seconds",
        "response_bytes",
        "sampled_process_peak_rss_bytes",
        "sampled_cpu_percent_peak",
        "sampled_device_used_vram_peak_mib",
        "sampled_device_gpu_utilization_peak_percent",
        "torch_peak_allocated_bytes",
        "torch_peak_reserved_bytes",
    ]
    with (benchmarks / "results.csv").open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    feature_lines = [
        "# Actual synthetic feature matrix",
        "",
        "REAL MODEL + REAL HTTP, both final profiles. Expected-marker checks are deliberately limited; they are not a private-document quality benchmark.",
        "",
        "|Profile|Fixture|HTTP|Expected marker|Native categories|Out-of-frame boxes guarded|",
        "|---|---|---:|---|---|---:|",
    ]
    for row in capabilities:
        feature_lines.append(
            f"|{row['profile']}|{row['fixture']}|{row['http_status']}|{row['expected_marker_found']}|{','.join(row['categories'])}|{row['geometry_out_of_bounds']}|"
        )
    feature_lines += [
        "",
        "Source images/hashes/expected text: `tests/fixtures/manifest.json`. Complete responses: `benchmarks/<profile>/response-<fixture>.json`.",
        "",
        "PNG/JPEG/WebP decoding and real inference were exercised; PDF is unsupported415. Corrupt input422 is the expected rejection, not a failed OCR result mapped as success. Tables/merged headings remain native HTML; chart captions/Picture are not numerical chart reconstruction. Formula output retains native LaTeX. Model reading order is retained, not independently corrected. Rotated/skewed boxes stay in the provided image's frame; no rotation angle is invented.",
        "",
        "Blank is text-empty but can produce a hallucinated Picture box; `geometry_status` documents this. All finite usable mapped boxes are validated against image bounds. No confidence calibration or production capacity claim.",
    ]
    (ROOT / "docs/FEATURE_SUPPORT_MATRIX.md").write_text(
        "\n".join(feature_lines) + "\n", encoding="utf-8"
    )

    examples = [
        "# Actual response examples",
        "",
        "All examples are from the final local real-model/real-HTTP runs on committed synthetic images. No mock or private document output. Full versioned bodies and metadata are linked below; native_output is retained in those files.",
        "",
    ]
    for title, name in [
        ("Single English", "english"),
        ("Two-image Batch", "batch2"),
        ("Table", "table"),
        ("Full page", "full_page"),
        ("Cropped region", "crop"),
        ("Corrupt input/error", "corrupt"),
    ]:
        file = f"response-{name}.json"
        response = json.loads(
            (benchmarks / "ocr-final" / file).read_text(encoding="utf-8")
        )
        examples += [
            f"## {title}",
            "",
            f"[Complete actual response](../benchmarks/ocr-final/{file})",
            "",
            "```json",
            json.dumps(response, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    examples += [
        "MOCR responses are under `benchmarks/mocr-vllm-final/`. Batch result objects are exactly the Single data schema; do not map the outer results list as elements. Native rectangles are not OpenThai four-point polygons. See API_CONTRACT.md."
    ]
    (ROOT / "docs/REAL_RESPONSE_EXAMPLES.md").write_text(
        "\n".join(examples) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "profiles": len(profiles),
                "measured_http_requests": len(rows),
                "source_hashes_match": True,
            }
        )
    )

    lines = [
        "# Measured benchmark report — 2026-11-19",
        "",
        "Only local synthetic tests. Full machine-readable measurements: [results.json](../benchmarks/results.json), [results.csv](../benchmarks/results.csv). Raw responses and source SHA-256 values are in each final profile directory.",
        "",
        "## Machine and methodology",
        "",
        f"Windows10 Pro19045; Intel i7-13700K16physical/24logical cores; RAM{hardware['ram_total_bytes']:,}bytes. NVIDIA RTX4070,12282MiB VRAM, driver581.80. Native Python3.12.10/PyTorch2.5.1+cu121/Transformers4.51.3. Linux/vLLM0.17.1/PyTorch2.10.0+cu129/Transformers4.57.6. BF16 both. Shared workstation, not exclusive GPU or controlled power/thermal state.",
        "",
        "RSS/CPU sampling50ms and full-device GPU sampling200ms. CPU process percent can exceed100% on multicore. Sub-sample spikes can be missed. Full-device GPU/host RAM include other applications. Linux psutil host values describe the Docker Linux VM, not Windows physical RAM. vLLM allocates the model in a child: parent RSS/Torch allocator/CPU values must NOT be presented as whole-engine resources. Cgroup memory includes file cache and children; it is not reduced by subtracting reclaimable cache.",
        "",
        "There are37 measured inference-facing HTTP requests/profile (74total). Each profile additionally issues one authenticated readiness GET and one busy429 probe, so the benchmark driver sends78HTTP calls total across the two final runs. Expected corrupt422 and deliberate deadline504 are not mislabeled HTTP200 successes. Each real-response verification checks finite usable geometry, bounds, exactSingle/Batch data equivalence for1/2/4/8, ordering, partial failures and recovery. Small fixture markers are checked, not a general OCR CER benchmark.",
        "",
        "## Final resource observations",
        "",
        "|Profile|Model load s|Sampled API process peak RSS bytes|Full-device VRAM peak MiB|API process CPU peak %|GPU peak %|",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for p in profiles:
        resources = p["resources"]
        lines.append(
            f"|{p['profile']}|{p['load_seconds']:.3f}|{resources['sampled_process_peak_rss_bytes']}|{resources['sampled_device_used_vram_peak_mib']}|{resources['sampled_cpu_percent_peak']}|{resources['sampled_device_gpu_utilization_peak_percent']}|"
        )
    cgroup = profiles[1]["cgroup"]
    lines += [
        "",
        f"Linux/vLLM experiment:6,442,450,944-byte cgroup, no swap,4CPU cap. Kernel memory.peak={cgroup['memory.peak'].strip()}bytes. memory.events: `{cgroup['memory.events'].strip().replace(chr(10), '; ')}`. Container exit0/OOMKilled=false. **memory.max pressure is real;6GiB does not establish a safe production margin.** Much of startup includes snapshot hash verification and cached weight pages; do not erase this pressure from the reported peak. No OOM was observed in these runs; no deliberate real OOM was induced on the shared GPU. Resource-exhaustion error handling has explicit test-double coverage.",
        "",
        "## Repeated latency (seconds)",
        "",
        "Three warm requests/resolution; p50 median, p95 nearest-rank=max with n3. This is not a stable tail estimate or a model-only speed ranking; runtimes, host activity and kernel warmup differ.",
        "",
        "|Profile|Input resolution|n|p50|p95|",
        "|---|---|---:|---:|---:|",
    ]
    dimensions = {
        "resolution_small": "400x200",
        "resolution_medium": "800x400",
        "resolution_large": "1200x800",
    }
    for p in profiles:
        for row in p["resolution_latency"]:
            lines.append(
                f"|{p['profile']}|{dimensions[row['fixture']]}|{row['n']}|{row['p50_seconds']:.3f}|{row['p95_nearest_rank_seconds']:.3f}|"
            )
    lines += [
        "",
        "Full-page fixture1000x1400 is downsampled under the model1,003,520-pixel processing budget. Original input dimensions and actual model dimensions are included in every response. Accepted decode4MP and model processing1MP are different limits.",
        "",
        "## Sequential Batch",
        "",
        "|Profile|Images|HTTP wall s|Images/s|Exact Single data equivalence|",
        "|---|---:|---:|---:|---|",
    ]
    for p in profiles:
        for row in p["batch_latency"]:
            lines.append(
                f"|{p['profile']}|{row['images']}|{row['latency_seconds']:.3f}|{row['images_per_second']:.3f}|{row['single_equivalence']}|"
            )
    load = json.loads((benchmarks / "load-profile.json").read_text())
    images = json.loads((benchmarks / "docker-images.json").read_text())
    lines += [
        "",
        "Batch is a sequential API loop with one owned GPU worker, not native GPU batching. Mixed Batch has2success/1corrupt error. Real deadline504 retains the active slot (next request429), followed by successful recovery200. No durable queue or hard-hang recovery claim.",
        "",
        "## Load and disk measurements",
        "",
        f"Explicit native load/reload in one fresh process: first{load['measurements'][0]['seconds']:.3f}s; cache-warm reload{load['measurements'][1]['seconds']:.3f}s. Each includes pinned snapshot integrity verification. True cache-flushed disk-cold load was NOT measured; caches were not flushed on a shared workstation. HTTP model startup includes additional runtime/thread/processor overhead and is reported separately above. Warm inference reuses the model; it does not load weights again.",
        "",
        "Each model has6,078,431,736safetensors bytes (verified hashes). Downloaded snapshot tree OCR6,090,160,451bytes; MOCR6,090,084,274bytes, including tokenizer/code/notices/local download metadata. Native venv164,673,301bytes excludes reused system packages/CUDA Torch; it is not the complete dependency footprint.",
        "",
        "|Docker profile|Docker-reported image Size bytes|Apparent root filesystem bytes without weights|",
        "|---|---:|---:|",
    ]
    for image in images:
        lines.append(
            f"|{image['image']}|{image['logical_image_size_bytes']}|{image['root_apparent_bytes_without_models']}|"
        )
    lines += [
        "",
        "Apparent filesystem size was measured with `du -sbx /` in an unmounted container. Add the chosen6.09GB snapshot to that profile's installed filesystem footprint; this is NOT host incremental/VHD disk allocation. Shared image layers and separate model snapshots are distinct. Two model downloads, caches and testing images consumed local disk; no models/environments are committed.",
        "",
        "## Automated verification and unresolved items",
        "",
        "Native unit/contract/error/security tests56passed,0failed. Same56passed in fresh CPU Docker dependencies (model test double); real loopback TCP test included. Ruff and compile checks are separately recorded in validation.json. CPU Docker build/start/auth/fail-closed checks pass, source11/11files match both images. Linux/vLLM Docker runs the real model; its final exit0/OOMKilled=false is recorded. Native full model suites are scripts, not mocked pytest claims.",
        "",
        "Observed compatibility failures: OCR/Transformers4.56.1 processor video_processor error; pinned4.51.3 works. MOCR/4.51.3 processor constructor TypeError remains BLOCKED; the separate Linux/vLLM profile works without changing model code. CPU inference is untested because the shared host had insufficient comfortable free RAM for a float32~12.16GB weight load plus activations; it was not deliberately exhausted. This is not a measured CPU minimum.",
        "",
        "Remaining warning: vLLM child emits an NCCL process-group teardown warning. Explicit engine-core cleanup removed the earlier unexpected-engine-death shutdown error; the warning remains, so no claim of leak-free sustained lifecycle. Memory.max pressure at6GiB and no dedicated-host sustained test prevent a production-capacity guarantee. No historical OCRLab502 root cause is inferred from these experiments.",
        "",
        "No CDGS/Railway/Vercel deployment, private documents, existing DB, weights training, model routing change or slides. See HANDOVER.md for operator qualification and rollback steps. Review-ready Draft delivery is distinct from production acceptance.",
    ]
    (ROOT / "docs/BENCHMARK_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
