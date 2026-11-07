# Durable OCR jobs

The workflow submits a short HTTP request, then polls PostgreSQL-backed state.
It no longer keeps the browser's `/run` connection open during Global Layout OCR.
Historical API clients may still use `/run`; browser legacy callers also use jobs.

## API

- `POST /api/test-cases/{id}/jobs`: `{pipelines: [...], idempotency_key: "uuid"}`; commits before HTTP202. No inference in the request handler.
- `GET /api/test-cases/{id}/jobs`: latest job, or null. Used to recover navigation/refresh.
- `GET /api/ocr-jobs/{id}`: compact progress, timestamps, safe failure information and result IDs. No input images, GT, config snapshot, auth header or private lease owner.
- `GET /api/ocr-jobs/{id}/results`: that job's persisted runs in submitted pipeline order. Does not initiate inference. Partial results remain accessible.

Statuses: queued, running, completed, partial_success, failed. Cancellation is deliberately not exposed: cancelling a browser request cannot reliably stop upstream inference. `cancelled` is reserved, never reported for uncontrolled work.

Progress is committed completed field/pipeline units, including failures, divided by the submitted field/pipeline count. Completed pipelines have every field checkpointed. Concurrent groups have no single current pipeline, so that value may be null. Progress advances at bounded batch checkpoints; it is not a timer approximation. The elapsed display uses a real server start timestamp and browser clock, independently of progress.

## Persistence and execution

Additive migration `0012_ocr_jobs` adds only `ocr_jobs`. No existing OCR/GT schema or historical data is rewritten. The job references its PipelineRun IDs; existing unique `(pipeline_run_id, field_index)` constraints continue protecting field identity. Config/model selections are snapshotted privately at enqueue, so registry edits do not silently change a running job.

The existing single Railway service hosts one lifespan-supervised consumer. PostgreSQL is the authority, not the asyncio task/event. Claims use a PostgreSQL transaction advisory lock and `FOR UPDATE SKIP LOCKED`, allowing only one unexpired active job across consumers. Claims increment attempt count, assign a unique process owner and a90-second lease. An independent session/thread heartbeats every10seconds. Every checkpoint/final transition requires the same owner and an unexpired lease in the committing transaction. A stale process cannot commit results after another owner claims the job.

Each bounded field group persists results and progress atomically. Recovery skips already-persisted `(field, pipeline)` results and reuses original parent run IDs. Failed OCR units are terminal for that job, not blindly retried. In-flight uncommitted units may be inferred again after a crash: external HTTP is **at least once**, committed outputs are deduplicated. This is not an exactly-once upstream guarantee.

Task/field/batch defaults remain4/8/4, hard image batch ceiling30, one active job. No unbounded fanout or extra cloud worker/queue service. Existing DET/REC routing, normalization, ordering, perspective crops, ROI, GT association and partial failure parsing remain unchanged.

## Railway sleep

Production inspection confirmed one replica and `sleepApplication=true`. Railway documents outbound packets/database activity as activity: [serverless inactive detection](https://docs.railway.com/deployments/serverless#inactive-service-detection). Only active jobs heartbeat; browser traffic is unnecessary to maintain that activity. Startup scans queued/expired work and waits for live leases to expire. The idle consumer does not periodically query PostgreSQL, so it does not intentionally keep the service awake while idle. Sleep settings and paid service count are unchanged.

Queue durability does not make ephemeral uploaded files durable. A process restart in the same container preserves its source. Container replacement may lose old local uploads; a missing source produces a safe failed job, preserving committed partial results. There is no fabricated source/reconstruction. Guaranteed completion across source loss requires durable storage, which is not provisioned by this release.

`OCR_JOBS_ENABLED` defaults true; false disables consumption/submission for operational rollback. It is optional, not a new required secret. Keep one Uvicorn process/replica with the current local storage architecture.

## Browser and security

The browser stores only job/request IDs, polls every2.5seconds, and backs off to15seconds after connectivity failures. Polls never submit another job. The same request key returns the same job even after completion; a different key for the same active case/pipeline selection returns the active job. A different selection conflicts. Backend constraints protect multiple tabs independently of browser storage.

Completed and partial-success jobs open Ground Truth only after persisted usable results can be read. Partial results retain a visible failure warning. Failed/cancelled jobs never navigate as success merely because progress is100%. The browser retains its job reference; opening GT acknowledges the job so returning to Pipelines does not repeatedly redirect. A results link remains available if automatic navigation fails. See the [workflow regression audit](ocr-workflow-regression-audit.md).

The independent PR13 review found that empty successful reads stopped too early and failed reads retried indefinitely. Terminal result verification now has a six-attempt / 30-second browser deadline, including aborting a pending fetch. Empty results and transient errors share that budget; permanent client errors stop immediately. An explicit recheck reads the saved job without submitting inference. A separate, clearly labelled rerun creates a new execution. See the [independent review](pr13-independent-review.md) for outstanding release gates.

The application currently has no per-user authentication; job UUID visibility follows the existing case/result access model, not a new access-control boundary. Job endpoints are no-store. Existing accepted origins remain explicit; no wildcard or credentials exposure was introduced.

See [recovery procedure](ocr-job-recovery.md), [timeout evidence](ocr-timeout-root-cause.md), and [validation](ocr-production-validation.md).
