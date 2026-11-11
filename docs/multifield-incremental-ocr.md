# Incremental OCR for 80 Fields

This upgrade starts from main `5e2f846b5838735d70b5f54f54818a7e084fc0be` (PR #13 already merged). It uses a new branch/PR; it does not reopen PR #13. Final test/resource and deployment evidence is recorded separately in the release gate ledger.

## Execution and durability

New submissions accept 1–80 Fields and 1–3 selected Pipelines: at most 240 logical units in one Job. Existing model configurations are retained. Image/PDF limits remain 2 MP, 10 MiB, 20 pages, default 140 DPI for new PDFs. No image downsampling or metric/model changes are introduced.

The new 240-unit capacity belongs to the durable `/jobs` executor used by the UI. The old synchronous `/run` compatibility endpoint retains its previously supported 24-unit budget and explicitly directs larger callers to `/jobs` with HTTP409 before inference. This is not a limit on a durable Job and never asks a user to divide the 80-Field Job. It prevents bypassing the bounded executor through the old in-memory collector.

`IncrementalGlobalJob` executes Pipeline-first, then Field order. It holds one prediction/transport result at a time, closes the source image after execution, and uses a fresh SQLAlchemy Session for each durable transaction. The original worker Session does not load the case's growing result history. No database connection/transaction spans an external inference await.

The existing unique `(pipeline_run_id, field_index)` key is retained. A fenced transaction validates status, lease owner and expiry, writes the prediction, then advances counters in the same commit. Recovery reconciles counters from committed rows and skips those rows. Parent run IDs and Job ID remain stable. A lost commit acknowledgement can be reconciled without duplicate persisted output. External inference before an unacknowledged/uncommitted result may be repeated; this is not exactly-once external inference.

Prefill is sequential, including its hidden Pipeline. When its selected configuration matches, committed inference is reused. A compact per-Field draft is patched server-side into the JSON checkpoint; earlier raw responses are not repeatedly fetched/rewritten. Final prefill locks the case and checks that GT remains pristine. User edits/confirmed GT are preserved, and evaluation still requires confirmation.

New submissions are validated at admission. Already accepted older legacy six-Pipeline snapshots can recover under their immutable configuration; the new limit does not invalidate those Jobs. Historical results remain readable. Source files that are absent or unsupported cause an explicit failure, not fabricated outputs.

## Measured memory changes

The baseline retention probe held up to 240 OCRField ORM objects. The incremental implementation holds at most one during its commit probes. Final text aggregation uses scalar streaming, without hydrating the complete result relationships.

Encoded source caching is capped at 512 KiB after the source has been decoded. Large high-entropy PNGs otherwise duplicate the decoded page for the entire long Job. Large whole-page crops are encoded only when needed with the same lossless encoder; tests verify exact crop hashes for both retained compact encodings and released large encodings. There is no downsampling or OCR-quality change.

Repeated Gateway failures also exposed a real Future/traceback ownership cycle in batching: with cyclic GC disabled, twenty completed failing calls retained twenty upload owners; explicit GC released them. Clearing the completed send/flush Future references and entry list releases all twenty immediately after completion callbacks, without forced GC. Existing response slicing, error codes/details/request IDs and retry hints remain intact. Native release also runs once after an execution frame has closed its images, before terminal status permits large result readers.

Dataset export previously decoded the same source for every Field. It now owns one decoded page for adjacent Fields, closes that owner before moving to another page, and preserves exact crop pixels. ZIP compression consumes 64 KiB views, and the archive spills after 512 KiB to the existing temporary filesystem. Temporary file cache remains included in cgroup measurements.

An allocator diagnostic found approximately 19.6 MB of freed native pages retained before ZIP compression; trimming after writing the member was too late to avoid the peak. Best-effort native release is therefore limited to large source-read and encoded-crop boundaries (at least 512 KiB), before allocating the next owner/compression output. It does not force GC or release live buffers. Small Field exports do not invoke the hint per Field. Unsupported allocators retain the existing no-op behavior. The measured diagnostic cost was milliseconds, not an artificial per-request delay.

## GT, progress and network behavior

The atomic bulk GT endpoint resolves all Field IDs before changing any GT, applies the existing invalidation rules, and returns one saved case instead of returning the full case eighty times. The frontend only falls back to individual writes when the old server reports the missing route (`404 Not Found`), not a semantic missing-Field error.

Polling uses compact server-owned Job state: current Pipeline/Field, persisted counts and timestamps. It does not fetch detailed predictions on every poll. Result details load after completion/on demand. Existing History `view=summary&latest=true` and request coalescing are retained. Large saved-case detail/export requests still contain their intended complete data; the 80-Field fixtures' response sizes are measured, not assumed constant.

An extended 240-result test with 4,000 Thai characters per prediction exposed a separate saved-response peak: the original whole JSON unicode string plus UTF-8 body copies raised kernel peak to 448,974,848 bytes for a roughly 20.5 MB response. Saved-case/results/GT/evaluation responses now validate and count one bounded JSON pass before sending success headers, then stream an identical second encoding in chunks no larger than 64 KiB. The complete body and exact Content-Length remain unchanged. No large temporary response file/cache is created. Encoder ownership is released on normal completion and disconnect, including disconnect before the first body chunk. This trades a second encoding pass for bounded transient memory rather than truncating predictions.

The extended queue/recovery run independently completed all 240 outputs after a controlled worker SIGKILL, preserving 100 previously persisted IDs with attempt count 2. Queue capacity five and idempotency at capacity were verified. Its functional PASS is distinct from the memory verdict: the same run still recorded an over-target peak during physical oversized-Gateway-response rejection, so it cannot by itself clear the release gate.

That rejection path included approximately 11.8 MB of kernel TCP receive backlog. Gateway connections now request a 256 KiB SO_RCVBUF (Linux may double this accounting), retaining verified TLS, no environment proxy, no automatic transport retries and blocked redirects. The physical decoded response cap remains 8 MiB. A real loopback transport test verifies the socket bound and unchanged 3 MB response bytes; no arbitrary request delay was added. Final release acceptance must use the complete current candidate, not the earlier socket-only diagnostic.

Repeated leaf requests also rebuilt the same OpenSSL CA certificate store on every call. A controlled full-matrix diagnostic that changed only verified TLS-context reuse reduced peak from 412,729,344 to 395,911,168 bytes. The client now caches one verified CA context per process while preserving separate client/connection lifetimes, certificate validation and hostname checking. No certificate verification is disabled, and the context is not mutated after construction. Regression coverage verifies both the shared trust store and independent transport pools. Final acceptance uses the rebuilt application image without diagnostic monkeypatches.

240 logical units are not 240 Gateway requests. For three detected regions per Field, three selected Pipelines plus a separate hidden prefill Pipeline require up to `80 × 4 × (1 DET + 3 REC) = 1280` leaf HTTP requests before retries. More regions can require more calls. Full resource workloads use an isolated local mock, not the live CDGS budget. Production acceptance must use a small synthetic workload.

## Verification and limitations

Tests cover mapping/ROI/order, atomic GT invalid-ID rollback, per-Field metric/export completeness, six interruption boundaries, matching-prefill reuse/recovery, all-failed terminal behavior, old six-Pipeline recovery, and exact exported pixels/resource ownership. Browser tests cover real local 40/60/80 × 3 Jobs, three-selection admission, last-Field focus/scroll, bulk GT, mobile refresh and no duplicate submission.

Resource tests progress through three trials each at 40, 60 and 80 Fields under 512,000,000 bytes / 1 CPU / no swap. The target is kernel memory.peak ≤409,600,000 bytes, including realistic charged file cache. An explicit local cache reserve avoids a warm shared Docker image layer concealing the earlier cold-cache case; it is not subtracted from results. A separate failure/recovery matrix checks valid large transport responses, rejected outputs, retries, queue pressure and worker interruption.

The historical HTTP 502 cause remains unconfirmed. A controlled SIGKILL exit 137 with OOMKilled=false is not evidence of an OOM. Passing these synthetic workloads does not establish unlimited capacity or guarantee every adversarial combination of public requests.

## Operations

No schema migration, dependency, paid plan, replica, project or durable-storage migration is required. Keep Railway Free, 512 MB, one CPU/replica and existing sleep/health configuration. No source files or production records are deleted. Public shared workspace exposure and ephemeral-upload recovery limitations remain explicitly accepted product risks; this change adds no authorization. REQ-12 remains out of scope.

Rollback must drain/wait for active large Jobs before reverting to an older 12-Field implementation. Database schema remains compatible, but old code is not a safe executor for an active 80-Field snapshot. Reverting a deployment cannot recover ephemeral uploads; do not claim otherwise. If a live defect occurs, stop new submissions operationally and prefer a reviewed forward fix preserving the durable Job/checkpoints.
