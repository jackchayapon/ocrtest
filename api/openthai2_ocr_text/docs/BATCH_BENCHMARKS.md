# Local real-model Batch verification

Executed on 13 November 2026 using the installed revision `39fa41bdd49f067ba41b1d9de79c06ab506d67d4`, the standalone Dockerfile, Python 3.12/Linux, one CPU, one executor thread, a 1,536 MiB memory limit and no swap. Weights were mounted read-only and verified by the startup SHA-256 manifest. Input alternated the packaged Thai/English PNG and a generated blank JPEG. All Batch results matched repeated single-image results, including text, lines, geometry and confidence.

Each row summarizes three warm trials over loopback. Batch per-image time is amortized wall time. CPU and RSS/cgroup values come from a 50 ms sampler included in resource totals. Short CPU windows can exceed 100% within scheduler accounting periods.

| Images | Mode | Median wall seconds | Amortized seconds/image | Images/second | HTTP requests | Sampled peak cgroup MB | Sampled peak RSS MB | Median sampled CPU |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
|1|Repeated single|0.101598|0.101598|9.843|1|469.99|284.31|99.55%|
|1|Batch|0.089584|0.089584|11.163|1|469.99|284.31|101.88%|
|2|Repeated single|0.232466|0.116233|8.603|2|569.19|383.32|100.40%|
|2|Batch|0.241399|0.120700|8.285|1|569.16|383.32|100.84%|
|4|Repeated single|0.443776|0.110944|9.014|4|569.50|383.33|100.02%|
|4|Batch|0.436792|0.109198|9.158|1|569.54|383.33|99.41%|
|8|Repeated single|0.867788|0.108474|9.219|8|569.98|383.36|99.67%|
|8|Batch|0.852203|0.106525|9.387|1|569.97|383.37|100.10%|

The 24 timed trials had zero request or item errors. Separate real HTTP mixed-valid/corrupt input returned ordered success/error/success. Startup to readiness took1.875seconds. The first single request took0.1464seconds. In a fresh process, first Batch8 took0.7812seconds and warm Batch8 took0.7018seconds. Provisioned weights and host filesystem caches were reused.

Kernel `memory.peak` for the final-source matrix was577,847,296bytes. RSS high-water was385,036,288bytes. A separate eight2MP synthetic-image case completed in1.2754seconds, matched Single results and reached kernelpeak577,671,168bytes. Both containers had zero OOM/max events. Source hashes matched9/9files. A local container restart passed health, authorized readiness, wrong-key rejection and real Single/Batch inference. Runtime UID10001, pip check, read-only root/model,1CPU and1536MiB/no-swap settings were verified.

The preceding candidate had37tests and24trials, with final-source kernelpeak352,837,632bytes and an earlier peak573,382,656bytes. This pass has50tests and a freshly executed24-trial matrix after fail-closed authentication and Single upload cleanup fixes. Cache/shared-page charging changes cgroup totals, including totals below RSS in earlier runs. These experiments do not isolate a causal memory improvement. Kernel peaks include charged cache and samples can miss brief allocations. This evidence does not approve512MB standalone deployment.

The measurements show reduced HTTP request count. Latency differences were small in this loopback sample. Execution remains sequential and these trials do not establish a native-model batching speedup or CDGS production capacity. OCRLab's Railway container retains its separate 512 MB limit. This benchmark used the standalone container described above.

Reproduce after starting the local container with its verified model and private local key.

```sh
python scripts/benchmark_batch.py --url http://127.0.0.1:8091 --rounds 3 --output /private/path/batch-benchmark.json
```

Sanitized aggregates and evidence hashes are in [batch-benchmark.json](batch-benchmark.json). Current raw evidence remains in ignored `.runtime/openthai-finalize/`, with previous evidence preserved in `.runtime/openthai-batch/`. Direct-Docker missing-key tests returned503 protected APIs and200 liveness. Compose rejected an empty key before container creation. No live CDGS load tests were run.
