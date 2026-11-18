# Measured benchmark report — 2026-11-19

Only local synthetic tests. Full machine-readable measurements: [results.json](../benchmarks/results.json), [results.csv](../benchmarks/results.csv). Raw responses and source SHA-256 values are in each final profile directory.

## Machine and methodology

Windows10 Pro19045; Intel i7-13700K16physical/24logical cores; RAM34,111,770,624bytes. NVIDIA RTX4070,12282MiB VRAM, driver581.80. Native Python3.12.10/PyTorch2.5.1+cu121/Transformers4.51.3. Linux/vLLM0.17.1/PyTorch2.10.0+cu129/Transformers4.57.6. BF16 both. Shared workstation, not exclusive GPU or controlled power/thermal state.

RSS/CPU sampling50ms and full-device GPU sampling200ms. CPU process percent can exceed100% on multicore. Sub-sample spikes can be missed. Full-device GPU/host RAM include other applications. Linux psutil host values describe the Docker Linux VM, not Windows physical RAM. vLLM allocates the model in a child: parent RSS/Torch allocator/CPU values must NOT be presented as whole-engine resources. Cgroup memory includes file cache and children; it is not reduced by subtracting reclaimable cache.

There are37 measured inference-facing HTTP requests/profile (74total). Each profile additionally issues one authenticated readiness GET and one busy429 probe, so the benchmark driver sends78HTTP calls total across the two final runs. Expected corrupt422 and deliberate deadline504 are not mislabeled HTTP200 successes. Each real-response verification checks finite usable geometry, bounds, exactSingle/Batch data equivalence for1/2/4/8, ordering, partial failures and recovery. Small fixture markers are checked, not a general OCR CER benchmark.

## Final resource observations

|Profile|Model load s|Sampled API process peak RSS bytes|Full-device VRAM peak MiB|API process CPU peak %|GPU peak %|
|---|---:|---:|---:|---:|---:|
|ocr-final|13.047|5021184000|9228.0|615.0|99.0|
|mocr-vllm-final|99.845|1510055936|11290.0|374.3|99.0|

Linux/vLLM experiment:6,442,450,944-byte cgroup, no swap,4CPU cap. Kernel memory.peak=6442450944bytes. memory.events: `low 0; high 0; max 22727; oom 0; oom_kill 0; oom_group_kill 0`. Container exit0/OOMKilled=false. **memory.max pressure is real;6GiB does not establish a safe production margin.** Much of startup includes snapshot hash verification and cached weight pages; do not erase this pressure from the reported peak. No OOM was observed in these runs; no deliberate real OOM was induced on the shared GPU. Resource-exhaustion error handling has explicit test-double coverage.

## Repeated latency (seconds)

Three warm requests/resolution; p50 median, p95 nearest-rank=max with n3. This is not a stable tail estimate or a model-only speed ranking; runtimes, host activity and kernel warmup differ.

|Profile|Input resolution|n|p50|p95|
|---|---|---:|---:|---:|
|ocr-final|400x200|3|1.141|1.234|
|ocr-final|800x400|3|1.329|1.359|
|ocr-final|1200x800|3|2.313|2.375|
|mocr-vllm-final|400x200|3|0.535|0.565|
|mocr-vllm-final|800x400|3|0.487|0.543|
|mocr-vllm-final|1200x800|3|0.463|0.533|

Full-page fixture1000x1400 is downsampled under the model1,003,520-pixel processing budget. Original input dimensions and actual model dimensions are included in every response. Accepted decode4MP and model processing1MP are different limits.

## Sequential Batch

|Profile|Images|HTTP wall s|Images/s|Exact Single data equivalence|
|---|---:|---:|---:|---|
|ocr-final|1|2.047|0.489|True|
|ocr-final|2|5.343|0.374|True|
|ocr-final|4|12.266|0.326|True|
|ocr-final|8|12.703|0.630|True|
|mocr-vllm-final|1|0.854|1.171|True|
|mocr-vllm-final|2|1.862|1.074|True|
|mocr-vllm-final|4|3.920|1.020|True|
|mocr-vllm-final|8|7.465|1.072|True|

Batch is a sequential API loop with one owned GPU worker, not native GPU batching. Mixed Batch has2success/1corrupt error. Real deadline504 retains the active slot (next request429), followed by successful recovery200. No durable queue or hard-hang recovery claim.

## Load and disk measurements

Explicit native load/reload in one fresh process: first11.265s; cache-warm reload7.141s. Each includes pinned snapshot integrity verification. True cache-flushed disk-cold load was NOT measured; caches were not flushed on a shared workstation. HTTP model startup includes additional runtime/thread/processor overhead and is reported separately above. Warm inference reuses the model; it does not load weights again.

Each model has6,078,431,736safetensors bytes (verified hashes). Downloaded snapshot tree OCR6,090,160,451bytes; MOCR6,090,084,274bytes, including tokenizer/code/notices/local download metadata. Native venv164,673,301bytes excludes reused system packages/CUDA Torch; it is not the complete dependency footprint.

|Docker profile|Docker-reported image Size bytes|Apparent root filesystem bytes without weights|
|---|---:|---:|
|ocrlab-dots:cpu-test|372210586|1299588797|
|ocrlab-dots:vllm-test|9314247150|20897679127|

Apparent filesystem size was measured with `du -sbx /` in an unmounted container. Add the chosen6.09GB snapshot to that profile's installed filesystem footprint; this is NOT host incremental/VHD disk allocation. Shared image layers and separate model snapshots are distinct. Two model downloads, caches and testing images consumed local disk; no models/environments are committed.

## Automated verification and unresolved items

Native unit/contract/error/security tests56passed,0failed. Same56passed in fresh CPU Docker dependencies (model test double); real loopback TCP test included. Ruff and compile checks are separately recorded in validation.json. CPU Docker build/start/auth/fail-closed checks pass, source11/11files match both images. Linux/vLLM Docker runs the real model; its final exit0/OOMKilled=false is recorded. Native full model suites are scripts, not mocked pytest claims.

Observed compatibility failures: OCR/Transformers4.56.1 processor video_processor error; pinned4.51.3 works. MOCR/4.51.3 processor constructor TypeError remains BLOCKED; the separate Linux/vLLM profile works without changing model code. CPU inference is untested because the shared host had insufficient comfortable free RAM for a float32~12.16GB weight load plus activations; it was not deliberately exhausted. This is not a measured CPU minimum.

Remaining warning: vLLM child emits an NCCL process-group teardown warning. Explicit engine-core cleanup removed the earlier unexpected-engine-death shutdown error; the warning remains, so no claim of leak-free sustained lifecycle. Memory.max pressure at6GiB and no dedicated-host sustained test prevent a production-capacity guarantee. No historical OCRLab502 root cause is inferred from these experiments.

No CDGS/Railway/Vercel deployment, private documents, existing DB, weights training, model routing change or slides. See HANDOVER.md for operator qualification and rollback steps. Review-ready Draft delivery is distinct from production acceptance.
