# OCRLab 80 Fields × 3 Pipelines — verified release candidate

Date: 2026-11-11. Branch `feat/multifield-incremental-ocr`, base `5e2f846b5838735d70b5f54f54818a7e084fc0be`. PR #13 is already merged; this upgrade uses a new PR. This is the pre-merge verification record. Actual merge/deployment/live results are recorded in the release journal and final delivery report, not claimed in advance.

## Final independent results

- Full backend: **679 passed / 0 failed / 0 errors / 0 skipped**, observed exit 0, PostgreSQL included (199.11 seconds).
- Full Playwright: **214 passed / 0 failed / 0 skipped**, observed exit 0 (6.3 minutes), against an isolated real local backend.
- TypeScript, ESLint, production build, Ruff, diff checks and clean local Alembic migration/schema checks passed. No new migration or dependency change.
- Tested Docker image matches all **84/84** backend Python source hashes. [Aggregate evidence](multifield-memory-evidence.json) binds source/test and evidence SHA-256 hashes. Raw probes/private runtime logs remain ignored.

| One durable Job | Fresh mixed trials | Worst kernel memory.peak |
|---|---:|---:|
| 40 × 3 | 3/3 | 383.365 MB |
| 60 × 3 | 3/3 | 389.820 MB |
| 80 × 3 | 3/3 | 388.764 MB |
| Extended errors/queue/recovery | All 19 phases | 409.559 MB |

Memory limit is 512,000,000 bytes, 1 CPU, no swap. Worst measured peak **409,559,040 bytes**, leaving **20.008%** RAM against the 409,600,000-byte acceptance ceiling. This includes charged file cache with an initial 220 MB cache reserve; no cache is subtracted. No observed OOM or memory.max event. Sampled RSS high-water in the extended matrix is 211,505,152 bytes. See [comparison chart](multifield-memory-comparison.png).

The first whole-response implementation exceeded the target at 448,974,848 bytes. Complete bounded JSON encoding, bounded receive sockets, deterministic Future/traceback owner release, encoded-source lifetimes and reuse of the verified TLS CA context address separately measured allocation paths. Counterexamples remain in the evidence; passing normal trials never erased an extended failure.

## Correctness and recovery

Pipeline-first execution persists every Field before advancing. One Job supports 80 Fields × 3 selected Pipelines without manual splitting. One active executor and queue capacity five remain unchanged. Hidden prefill may add upstream work; logical unit counts are not HTTP request counts. No resampling, OCR text truncation, GT/metric formula or model routing change.

The final extended matrix verified valid 3.33 MB numeric responses, 128 DET regions, 32,768-character REC; explicit rejection above those limits and the 8 MiB transport cap; bounded 429/503/timeout/wrong-contract behavior; partial success; 40×1/60×2/80×1; and complete 4,000-character × 240 persisted results (20,509,949 HTTP body bytes). A controlled worker SIGKILL recovered **240 unique outputs**, preserving **100 committed IDs**, attempt count 2, OOMKilled=false. All pre/post-restart peaks/events are retained. This is not a claim of exactly-once upstream inference.

Old adapter fixtures still exercise every configuration in groups of at most three with their original ROI/hash/status/export assertions. No tests were deleted or skipped. The old synchronous global `/run` compatibility path retains its 24-unit budget and directs larger callers to durable `/jobs`; it cannot bypass the bounded executor. Old accepted six-Pipeline snapshots still recover.

Bulk GT uses one atomic request, rejects invalid/duplicate IDs and preserves existing invalidation rules. Missing-route compatibility fallback is limited to literal HTTP404 Not Found. Browser coverage includes 40/60/80×3, final Field focus, mobile refresh, storage denial and no duplicate submission. History summary/latest optimization remains unchanged.

## Release and accepted limitations

Use the existing normal new-PR merge and main auto-deploy, never direct/force push or re-merge PR13. Recheck exact GitHub head/checks and deploy SHA. Railway stays Free/512 MB/1 CPU/1 replica, PORT8000, PDF140, healthcheck180 seconds and sleep enabled. Vercel stays the existing Hobby project. No new subscription/resource/provider or additional hosting charge is introduced. Finite free-tier/CDGS quotas remain operational limits; do not auto-upgrade.

Fresh Neon verification is read-only metadata at revision0012 with ORM column compatibility; no user rows, schema migration, reset or deletion. Public shared read/write/delete/admin exposure is the accepted personal educational prototype requirement, not authentication. Existing ephemeral-upload risk remains; code rollback cannot restore files. Drain active80-Field Jobs before older-code rollback; prefer a reviewed forward fix preserving Jobs/checkpoints.

Resource tests use local synthetic Gateway responses. They establish a bounded synthetic envelope, not live CDGS capacity or unlimited adversarial concurrency. Production acceptance uses only a small owned synthetic document, two Fields and two Pipelines; the full240 workload is not run against CDGS. Historical HTTP502 root cause remains unconfirmed. REQ-12 is out of scope.
