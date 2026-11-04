# Production recovery — November2026

Status: corrected candidate implemented; final acceptance and deployment are not yet established. Existing production remains on Railway commit67df434dabed0eeb70a38009fc33fde0e12eba41. Vercel remains connected to Railway. Do not interpret local/mock passes as a verified production release.

## Completed independently

- Bounded pipeline workers and field crop groups; smaller per-owner response copying and leaf transport archive omission.
- Safe upstream-model diagnostics, selected query/count information and Linux memory readings.
- Regression tests, before/after A–G evidence and sequential real CDGS tests.
- Isolated PostgreSQL head0011_gt_prefill, no schema drift, no new migration.
- Render fallback blueprint and explicit data/storage/cutover/rollback gates.

## Current release blockers

- Railway rejected new staging provisioning under Free resource quota. Temporary service usage approval does not authorize upgrading the subscription.
- No authenticated Render deployment path was available. Render Free ephemeral storage is not a durable production replacement.
- Production uploads have no persistent volume; no approved existing object-storage credentials or newly verified recovery/restore evidence were available.
- Existing backend/UI baseline failures must be distinguished from new regressions in [validation](production-release-validation.md). No tests are disabled to hide failures.
- Candidate raw cgroup peak465.6MB remains above the preferred400MB objective; inactive file cache and anonymous RSS must be distinguished. Real cloud-parity resource acceptance is pending.
- Historical CDGS422 internal failure and historical Railway process exit cause remain unknown. Real shared-Gateway concurrent tests require operator permission.

No production user records, model definitions, secrets or deployment settings were changed. No historical uploads are claimed recoverable merely because metadata exists.

See [root-cause analysis](ocr-performance-root-cause.md), [migration/rollback](railway-render-migration.md), [validation](production-release-validation.md) and [performance results](../postman/staging/results-final.json).
