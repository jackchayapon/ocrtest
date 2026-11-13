# Local real-model Batch verification

Executed on 13 November 2026 using the installed revision `39fa41bdd49f067ba41b1d9de79c06ab506d67d4`, the standalone Dockerfile, Python 3.12/Linux, one CPU, one executor thread, a 1,536 MiB memory limit and no swap. Weights were mounted read-only and verified by the startup SHA-256 manifest. Input alternated the packaged Thai/English PNG and a generated blank JPEG. All Batch results matched repeated single-image results, including text, lines, geometry and confidence.

Each row summarizes three warm trials over loopback. Batch per-image time is amortized wall time. CPU and RSS/cgroup values come from a 50 ms sampler included in resource totals. Short CPU windows can exceed 100% within scheduler accounting periods.

| Images | Mode | Median wall seconds | Amortized seconds/image | Images/second | HTTP requests | Sampled peak cgroup MB | Sampled peak RSS MB | Median sampled CPU |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
|1|Repeated single|0.090100|0.090100|11.099|1|244.75|285.50|99.92%|
|1|Batch|0.088912|0.088912|11.247|1|244.75|285.50|96.05%|
|2|Repeated single|0.230570|0.115285|8.674|2|344.10|384.44|100.31%|
|2|Batch|0.213942|0.106971|9.348|1|344.07|384.44|100.09%|
|4|Repeated single|0.455518|0.113879|8.781|4|344.14|384.45|99.97%|
|4|Batch|0.453827|0.113457|8.814|1|343.87|384.45|99.74%|
|8|Repeated single|0.929244|0.116155|8.609|8|344.29|384.47|99.32%|
|8|Batch|0.882353|0.110294|9.067|1|344.37|384.48|99.96%|

The 24 timed trials had zero request or item errors. Separate real HTTP mixed-valid/corrupt input returned ordered success/error/success. Startup to readiness took 1.828 seconds. The first single request after initialization took 0.1334 seconds. In a fresh process, the first Batch of eight took 0.7948 seconds and the subsequent warm Batch took 0.7289 seconds. Provisioned weights and host filesystem caches were reused.

Kernel `memory.peak` for the final-source matrix was 352,837,632 bytes. Process RSS high-water was 386,232,320 bytes. A separate accepted-limit test with eight 2 MP synthetic images completed in 1.3192 seconds, matched its single-image reference, and reached a kernel peak of 349,331,456 bytes. Both containers reported zero OOM kills and no `memory.max` pressure events. All nine Docker application source hashes matched the final candidate.

An earlier run before the upload-cleanup correction reached 573,382,656 bytes under the same 1,536 MiB limit. Host cache reuse and shared file-page charging can change cgroup totals, including totals below RSS. These runs do not isolate a memory improvement caused by the cleanup change. Retain the earlier higher peak when sizing the service. Kernel peaks include charged file cache and sampled peaks can miss short allocations. This evidence does not approve a 512 MB standalone deployment.

The measurements show reduced HTTP request count. Latency differences were small in this loopback sample. Execution remains sequential and these trials do not establish a native-model batching speedup or CDGS production capacity. OCRLab's Railway container retains its separate 512 MB limit. This benchmark used the standalone container described above.

Reproduce after starting the local container with its verified model and private local key.

```sh
python scripts/benchmark_batch.py --url http://127.0.0.1:8091 --rounds 3 --output /private/path/batch-benchmark.json
```

Sanitized aggregates and evidence hashes are in [batch-benchmark.json](batch-benchmark.json). Raw local probes, logs and credentials remain in ignored `.runtime/openthai-batch/`.
