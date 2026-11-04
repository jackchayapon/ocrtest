# Recovery candidate validation

This file records actual checks, including baseline failures. Final rollout is blocked until cloud/storage/acceptance gates in [recovery status](production-recovery-2026-11.md) are satisfied.

## Current evidence

- Before final PostgreSQL assertion updates: candidate432 passed/59 failed/0 skipped; production-source baseline425 passed/59 failed/0 skipped. Exact failure IDs matched;7 new tests passed. Six PostgreSQL tests skipped without TEST_DATABASE_URL were actually enabled in both runs.
- Four outdated migration-head assertions were corrected to0011_gt_prefill. All four focused PostgreSQL tests then passed, including current dynamic workflow/reconnect, migration preservation/no drift and bulk-FK behavior. Final full backend:436 passed/55 failed/0 skipped; no new failures against the59-failure production baseline; four baseline failures resolved. Legacy tests are not all green.
- Targeted routing/resource checks:56 passed before observability-only addition; final focused resource/CDGS checks50 passed afterward.
- Ruff passes for changed source/new tests. Whole-repository Ruff has8 existing import-order findings outside changed production files; no blanket reformat/historical migration edit was used to hide them.
- Frontend typecheck, ESLint and production build passed. Final complete157-case Playwright:123 passed/34 failed; production-source152-case baseline:117 passed/35 failed; no new failure IDs. All five new frontend tests pass. One responsive dashboard case varied between runs, not claimed as a deterministic repair. Failed legacy scenarios are not marked passed or disabled.
- Isolated Docker backend: Alembic0011_gt_prefill(head), no new upgrade operations.
- Sequential real CDGS baseline Newman:10/10 HTTP calls,20/20 assertions. All seven version/weight combinations passed. No real concurrent Gateway load was performed.
- Local corrected candidate + real CDGS, isolated PostgreSQL/storage: Auto ROI returned1 region; manual adjusted crop483x62; DET6/REC5 succeeded; confirmed GT CER0/WER0/ExactMatch true; saved result, History/Matrix/Analytics, five-entry evaluation ZIP and two-page PDF preview passed. One diagnostic request used per_field with require_complete_gt and correctly received422; corrected to the source-required auto contract without rerunning inference. This was application validation, not CDGS422.
- Main after matrix:18/18 OCR HTTP runs, no OCR502/process crash/OOM; Gateway inflight <=2. Compare before evidence and residual memory risk rather than claiming unlimited capacity.
- Real candidate browser verified UI GT synchronization, confirmation, CER0/WER0/ExactMatchtrue, saved-result reload, History and Comparison with no console/API errors. It resumed the actual successful CDGS run after fixing the one-sided GT dead-end; no inference was repeated to hide that UI failure.
- The final backend rerun includes secret redaction before allowlisting error detail codes/types. An initial rerun hit Windows permission errors for the shared pytest temporary directory; it was rerun with a dedicated temporary directory, yielding the436/55 result above. This harness error is not counted as a product regression or a passing run.

## Evidence locations

Safe public comparison: [results-final.json](../postman/staging/results-final.json). Detailed local logs/XML: .runtime/recovery/pytest.xml, pytest-baseline.xml, backend-comparison.json, playwright-full.log, live-candidate-result.json, evidence/process.jsonl. These artifacts are excluded from Git and do not contain production documents/headers in published summaries.

Production deployment/real GUI acceptance, tested production rollback and upload restart durability are **not** certified by these local checks. No merge/deploy is authorized by a passing subset alone.
