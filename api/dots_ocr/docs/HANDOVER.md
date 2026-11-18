# Standalone service handover

Starting origin/main: `d0b929df4087477056c3f13a323eaf0dbd45784f`. Work is isolated on `feature/dots-ocr-api` in a separate worktree. Existing dirty/conflicted OCRLab work was preserved. All PR paths must start `api/dots_ocr/`.

No OCRLab, OpenThai source, Pipeline registration, database, CDGS infrastructure or Railway/Vercel deployment is part of this change. No slides were generated. Real tests use local synthetic fixtures exclusively.

## Ownership and operator checks

1. Review `MODEL_COMPARISON.md`, source manifest and upstream notices. Download model snapshots on an authorized machine using the pinned downloader. Do not mount writable, arbitrary remote-code directories.
2. Select exactly one compatible runtime profile. Native OCR uses Transformers4.51.3; MOCR requires the separate tested vLLM Docker profile. CPU model inference is not verified. Never infer hardware minima from weight file size alone.
3. Compare intended hardware with `BENCHMARK_REPORT.md`. The shared RTX4070 measurements are observations, not an SLA. Linux6GiB experiments may hit cgroup memory.max during weight verification/file-cache pressure even without an OOM. Establish a dedicated-host RAM/VRAM/latency envelope before production use; do not subtract file cache to declare headroom.
4. Mount exact snapshots read-only, keep API key private and outside Git, terminate TLS at the operator-managed ingress. Do not enable prompt/body/header/debug dumps. App request logging uses generated request ID, fixed route label, status and duration only. Startup logging exposes failure class only. Restrict third-party/runtime logs and audit their configuration before handling sensitive documents.
5. Start one worker; check authenticated readiness and a synthetic Single/Batch. An HTTP200 Batch can have failed items. Never interpret liveness as successful model loading.
6. Add operator-side per-client quotas/rate limiting, monitoring and a supervisor before public exposure. Authentication and one-slot admission do not prevent an authorized key holder from monopolizing compute. This service is stateless: it has no durable queue, output storage, exactly-once semantics or cross-replica limit.
7. Monitor request status/duration/429/504, process and whole-container memory, GPU memory and worker health. A long native kernel may outlive HTTP timeout; new work remains429 until that worker completes. A stuck process requires operator-controlled restart; no CDGS restart was performed here.

## Test reproduction

```sh
python -m pytest tests -q
python -m ruff check app tests scripts
python scripts/benchmark.py --output benchmarks/private/new-native-run
python scripts/verify_responses.py benchmarks/private/new-native-run
python scripts/profile_load.py
```

Fixtures were generated with a Thai-capable Windows Tahoma font; font binaries are not redistributed. To regenerate elsewhere, supply an authorized Thai-capable TTF to `scripts/generate_fixtures.py --font ...`. Generated files and manifest hashes are committed. No remote image download is involved in inference.

`benchmarks/results.json`/CSV summarize measured profiles and link complete synthetic responses. Native measurements include the API process's allocator/RSS. vLLM places inference in a child process: parent Torch allocator values do not represent the engine; use full-device and cgroup evidence and the stated sampling limits. Shared-host totals include other applications. An experiment that failed startup is reported BLOCKED with zero inference requests, never a successful benchmark.

## Update and rollback instructions for a teammate

No deployment commands were executed on CDGS. A future operator should build from a reviewed commit of this subtree, retain the old image/model manifest, drain the one active request, switch only this standalone service, and check authenticated readiness plus synthetic Single and Batch. On a verified regression, return to that service's previous image and matching model snapshot; there is no database migration or OCRLab change to undo. Never switch between model/runtime revisions without repeating mapping tests. Keep license/NOTICE files with snapshots.

Pending acceptance: CPU inference, true disk-cold/dedicated-host capacity, sustained/multi-client load, hard-native-hang intervention, and target CDGS server compatibility. These remain unverified, not inferred PASS from unit tests. A Draft PR is suitable for teammate review while these environment-specific acceptance items remain open.

Source identity note: original benchmark raw-byte hashes are retained. Git normalizes CRLF/LF for prompt.py and model-manifest.json; additional canonical LF hashes match committed blobs. Prompt AST/string and parsed model configuration are unchanged. See benchmarks/source-identity.json. No benchmark result or native output was fabricated or reclassified for this normalization.
