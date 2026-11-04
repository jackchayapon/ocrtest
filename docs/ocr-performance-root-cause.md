# OCR resource management: evidence and fix

The historical CDGS422 and Railway502 causes remain unconfirmed. On 4 November, Railway proxy logs recorded connection closure after roughly52–54 seconds followed by process startup, but no historical exit code/signal/OOM event was available. All seven selected model combinations passed sequential live tests. No weight aliases or Gateway routing have been changed by this release.

## Confirmed implementation risks

- One HTTP OCR lock does not limit the field/pipeline work created inside a run. Previously a group of up to30 fields could each gather every selected pipeline.
- Gateway responses were buffered then JSON-decoded, recursively redacted and retained with unused transport data. BatchGateway deep-copied the complete combined response for every owner before slicing result aliases.
- Registered batch paths remain authoritative for version/model queries. Batching groups by URL and exact query; there was no evidence of cross-model query mixing.
- HTTP422 was always labeled request_contract, even when CDGS returned UPSTREAM_MODEL_ERROR. Safe worker error type/code information was discarded.

## Changes

The initial PR used task/field budgets2/2. The final measured defaults are `OCR_MAX_CONCURRENT_TASKS=4`, `OCR_MAX_CONCURRENT_FIELDS=8`, `OCR_GATEWAY_BATCH_SIZE=4`. Pipeline-major admission within each bounded field group restores equal-query coalescing; returned results remain field-major/config-ordered. The Gateway contract cap remains30; smaller upstream chunks bound large REC allocations, including owners with many line crops. No field-by-pipeline task explosion is created.

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

## Full-scale follow-up — 5 November

All A–G scenarios still pass18/18. Calls are64, versus132 for the first PR candidate and60 for production-source baseline. Sized E is3766.94ms, RSS324.8MB/cgroup284.4MB; compact E is3271.88ms. This improves the first candidate tradeoff without pretending every workload is faster than baseline.

The 30-fields x12-pipelines API workload uses10 DET/REC compositions (two DET variants x five REC selections) plus two recognition-only pipelines. Synthetic per-field pixels and per-REC version/variant text prove ownership, order, confidence and geometry. Final-source three repetitions each persist360/360 correct fields,12 successful pipelines, no duplicate IDs, no502/OOM/restart. Each uses195 calls. Wall times:48.058,48.796,47.644seconds; peak RSS315.2MB, raw cgroup340.4MB. The full inventory and sampled working-set/cache accounting are in [full-scale evidence](../postman/staging/full-scale-results.json). Three samples do not establish sustained capacity. Maximum Gateway inflight in this full-scale shape is2; other A–G shapes reach4, bounded by the adapter budget.

Separate deterministic REC-worker failure injection produces300 correct successes plus60 expected failures with all360 records preserved; HTTP200 is not reported as12 successful pipelines. A separate production-source67df434 local control on the same30x12 shape reaches512MB cgroup and502, with Docker `OOMKilled=true`/exit137. This is an isolated synthetic reproduction, not proof of historical Railway exit cause.

Global timing now stores `wall_clock_v1` in the existing small provenance JSON. `processing_time_ms`/`wall_time_ms` measure each pipeline's first admitted field through its last completed field, including scheduler gaps between groups. `total_field_compute_ms` sums individual adapter durations; `run_wall_time_ms` includes the overall global operation through aggregation preparation (before final DB save/HTTP serialization). Gateway duration retains existing batch attribution. Historical values are not rewritten. Summary History never loads raw provenance merely to fetch timing; details identify legacy records and frontend labels explain mixed historical timing semantics.

## Post-release Dataset read path

The bounded production OCR canary passed, but the default Dataset list read exceeded45seconds. Its unchanged repository loop performed session.get per sample, triggering TestCase selectin run/field payloads. A50-field local synthetic control measures352 SQL queries/1,072,484 estimated fetched bytes before, versus6/20,415 after bounded bulk metadata loading. HTTP response remains27,962bytes and is identical in every value. SQLite elapsed178.06->20.00ms is not a prediction of Neon latency; the round-trip/query and payload reductions are the relevant evidence. Pagination/order, eligibility, labels, exclusions, source availability and exports remain unchanged. New1/50-row budget tests prohibit pipeline_runs/OCRField/archive fetches.

Unfiltered all-history Error Analysis also exceeded a45-second browser wait. That alignment/aggregation path is unchanged; the canary-filtered route returns200. No result truncation or altered error/normalization semantics was introduced to hide it. It remains an explicitly recorded performance limitation requiring separate profiling.
