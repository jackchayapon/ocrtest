# Production recovery — November2026

Status: **GO WITH DOCUMENTED RESIDUAL RISK** for release execution; full-scale local acceptance and final regression comparison passed without new failures. Existing production remains on Railway commit67df434dabed0eeb70a38009fc33fde0e12eba41 until the recorded release step. Vercel remains connected to Railway. Do not interpret local/mock passes as a verified production release before the actual canary.

## Completed independently

- Bounded pipeline workers and field crop groups; smaller per-owner response copying and leaf transport archive omission.
- Safe upstream-model diagnostics, selected query/count information and Linux memory readings.
- Regression tests, before/after A–G evidence and sequential real CDGS tests.
- Isolated PostgreSQL head0011_gt_prefill, no schema drift, no new migration.
- Render fallback blueprint and explicit data/storage/cutover/rollback gates.

## Release considerations

- Railway rejected new staging provisioning under Free resource quota. The latest user instruction accepts isolated local evidence followed by a bounded production canary; quota alone is not a release blocker. No subscription upgrade is authorized or performed.
- No authenticated Render deployment path was available; fallback is not needed while corrected Railway passes acceptance. Render Free ephemeral storage is not a durable production replacement.
- Production uploads have no persistent volume. The latest user instruction explicitly accepts disposable historical upload loss risk during deployment; no intentional deletion is authorized. Restart durability is not certified and no old upload is claimed recovered.
- Existing backend/UI baseline failures must be distinguished from new regressions in [validation](production-release-validation.md). No tests are disabled to hide failures.
- Initial candidate raw cgroup peak465.6MB was near the limit. The final30x12 workload passes three repetitions with peak raw cgroup340.4MB/RSS315.2MB. Cloud-parity acceptance still requires the production canary; mock measurements are not CDGS capacity certification.
- Historical CDGS422 internal failure and historical Railway process exit cause remain unknown. Real shared-Gateway concurrent tests require operator permission.

No production user records, model definitions, secrets or deployment settings were changed. No historical uploads are claimed recoverable merely because metadata exists.

See [root-cause analysis](ocr-performance-root-cause.md), [migration/rollback](railway-render-migration.md), [validation](production-release-validation.md) and [performance results](../postman/staging/results-final.json).
