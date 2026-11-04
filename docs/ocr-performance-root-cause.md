# OCR resource management: evidence and fix

The historical CDGS422 and Railway502 causes remain unconfirmed. On 4 November, Railway proxy logs recorded connection closure after roughly52–54 seconds followed by process startup, but no historical exit code/signal/OOM event was available. All seven selected model combinations passed sequential live tests. No weight aliases or Gateway routing have been changed by this release.

## Confirmed implementation risks

- One HTTP OCR lock does not limit the field/pipeline work created inside a run. Previously a group of up to30 fields could each gather every selected pipeline.
- Gateway responses were buffered then JSON-decoded, recursively redacted and retained with unused transport data. BatchGateway deep-copied the complete combined response for every owner before slicing result aliases.
- Registered batch paths remain authoritative for version/model queries. Batching groups by URL and exact query; there was no evidence of cross-model query mixing.
- HTTP422 was always labeled request_contract, even when CDGS returned UPSTREAM_MODEL_ERROR. Safe worker error type/code information was discarded.

## Changes

`OCR_MAX_CONCURRENT_TASKS=2` bounds adapter execution across fields in one manager. A fixed worker pool keeps deterministic order without creating one task per configured pipeline. `OCR_MAX_CONCURRENT_FIELDS=2` bounds eagerly prepared crops separately from the unchanged image-batch cap30.

Gateway parsing keeps the verified data/meta envelope and omits leaf raw_output transport archives; structured OCR text, polygons, scores, model_selection and trace metadata remain. No historical stored results are rewritten. BatchGateway copies only each owner's selected result slice and small metadata, preserving all result aliases and per-owner ordering.

Logs distinguish upstream_model from generic422 validation and retain allowlisted error types/codes, selected query identifiers, image count, active Gateway tasks and best-effort Linux RSS/cgroup readings. They do not log error messages/inputs, images, OCR text, Authorization, API keys or DB URLs. No retry or model fallback was added.

## Measured comparison

Same synthetic source images/ROIs and A–G shapes were used with one trial per profile/stage. Before:18 OCR runs,60 mock batch calls, no OCR502/OOM; sized E sampled RSS540.3 MB/cgroup511.9 MB and4 active Gateway calls. Candidate:18 runs succeeded, max Gateway inflight2; sized E RSS281.4 MB/cgroup465.6 MB. Work was traded for more, smaller batches; latency must be read alongside memory rather than assumed improved.

The local candidate cgroup also had about205 MB inactive file cache after the run. RSS and cgroup account for different memory; the raw cgroup peak remains above the preferred400 MB objective. This is a residual risk/headroom question, not permission to report281 MB as total container usage. Docker layer/cache ownership and warmup also limit a causal comparison of the two cgroup totals.

The simulator's ~3.33 MB numeric response is size-matched, not a captured CDGS tensor shape. Results show allocation pressure under that workload, not a proof of the historical production OOM hypothesis. Input is multipart PNG; production Base64 paths, full30-image batches, sustained load, multiple workers/replicas and real CDGS concurrency were not stress-tested.

## Verification

New tests cover fixed worker limits/order, shared manager budget across fields, failure isolation, model query preservation, archive omission without output loss, per-owner alias/geometry independence and redacted model-worker diagnostics without422 retry. Test-only batching fixtures explicitly opt into a larger budget to continue exercising a three-image batch. Four PostgreSQL tests had outdated head assertions; they now verify0011_gt_prefill while retaining their migration/data-preservation checks. No migration was added or edited.

Real candidate browser testing also reproduced an existing GT form dead-end: a saved Sub-fields-only value with empty Whole Field left Confirm disabled while hiding the synchronization controls. The form now offers synchronization when either side has text, with the empty source disabled. It does not silently overwrite GT or change metric semantics. Browser regressions cover both one-sided states.

See [release validation](production-release-validation.md), [recovery status](production-recovery-2026-11.md) and [performance evidence](../postman/staging/results-final.json).
