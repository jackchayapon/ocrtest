# Production recovery — November2026

Status: **RELEASED — GO WITH DOCUMENTED RESIDUAL RISK**,5 November2026. PR8 merged as b28f5d8193be9549e01b1aff9d6cc74809ef9144; the focused Dataset follow-up PR9 merged as a4dfb464dbaf2d3844035bef52a1ccb3c3d6bc39. Railway deployment471f2fc9-a4cc-4ded-b771-012fc9cf9c2a serves a4dfb46. Vercel production dpl_43zry3Abjxxx3nbX6QjXDGLRUvW2 serves b28f5d8; frontend source is identical in both merge commits. The public frontend still targets Railway. Final actual browser/API canary and read-only record preservation checks pass.

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
- Unfiltered all-history Error Analysis exceeded a45-second check; the scoped canary analysis route works. Its unchanged alignment path needs separate profiling. Dataset's pre-existing list amplification was fixed in PR9:50-sample production list now returns200 in2217.77ms, versus the earlier45-second timeout;352->6queries on the controlled local fixture with identical responses.

No production user records, model definitions, secrets or deployment settings were changed. No historical uploads are claimed recoverable merely because metadata exists.

See [root-cause analysis](ocr-performance-root-cause.md), [migration/rollback](railway-render-migration.md), [validation](production-release-validation.md) and [performance results](../postman/staging/results-final.json).

Final quality:449backend passes/55unchanged baseline failures; full Playwright126/34unchanged failures, plus focused Dataset UI4/4. TypeScript/ESLint/build/changed-file Ruff pass. Full repo still has8old import-order findings. No new migration or required secret. Optional OCR budgets are4tasks/8fields/4batch images.

Production canary: one real OCRPOST/two Auto+Manual fields on each deployed application version; final wall3345ms vs summed field compute6690ms, CER/WER0 and ExactMatchtrue for both. PNG/PDFpage2 UI, GT confirm/reload, History/Detail/Comparison, evaluation ZIP, single-sheet Excel and Dataset original-ROI PNG/hash/confirmed-GT pairing pass. UI download buttons also work. Nine checked routes return200 (Error Analysis scoped to the canary); no console/API5xx. All original149documents/115cases/564runs remain by PK inventory. Added only4synthetic documents/2cases/2runs across two controlled release canaries; no intentional deletion or data reset.
