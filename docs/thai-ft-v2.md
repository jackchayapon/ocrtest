# Thai FT v2

The fifth pipeline, `thai_ft_v2` (display name **Thai FT v2**), reuses the existing Benchmark batch composition with fixed, distinct routing:

| Pipeline | Detection | Recognition |
| --- | --- | --- |
| Benchmark | `POST /api/v1/text-detection-batches?version=6` | `POST /api/v1/text-recognition-batches?version=5` |
| Thai FT v2 | `POST /api/v1/text-detection-batches?version=6&model=thai_ft_v2` | `POST /api/v1/text-recognition-batches?version=6&model=thai_ft_v2` |

Both stages use repeated multipart `images`. Benchmark sends neither `model` nor `engine`. Thai FT v2 sends `model=thai_ft_v2` at both stages and never falls back to REC V5.

Flow: active canonical ROI PNG → DET → polygons in returned order → perspective crops from that exact PNG → REC batches → ordered PipelineRun boxes and text. Auto and Manual ROI both supply the selected crop. Hutch Full retains its separate Auto/full-page and Manual/crop behavior.

The model owner confirmed that `results[*].model = th_PP-OCRv5_mobile_rec` in Thai FT v2 REC output is an **old upstream metadata label awaiting cleanup**, not a routing instruction. Raw upstream metadata remains unchanged by normalization (existing image/secret redaction still applies). Application-facing model information uses `model_selection.model_name`, currently `PP-OCRv6_medium_rec`, with selected configuration `version=v6`, `variant=thai_ft_v2`. If that metadata is absent, the display identifies the selected Thai FT v2 V6 configuration rather than guessing an underlying architecture.

Live revalidation also observed REC in the `leaf-inference-v1` / `text_recognition_batch` envelope with `results[*].rec_text` and `rec_score`. The shared parser supports this verified format as well as the earlier `text` / `confidence` response; routing and raw payload preservation are unchanged. Some newer responses omit the stale per-result model label entirely; earlier responses containing it remain supported.

The existing Field GT lifecycle, metrics normalization, whitespace WER, weighted field aggregates, history and analytics apply to this pipeline. Dataset labels remain confirmed Ground Truth only, and missing source files remain unavailable for export. No migration or new environment variable is needed. Additive startup seeding adds the new config without overwriting existing pipelines. Readiness remains `unknown` when Gateway readiness does not report this variant.

The synthetic live-contract fixtures are in `backend/tests/fixtures/thai-ft-v2-{det,rec}.json`; they contain no credentials or private documents. Regression tests verify exact queries, image bytes/order, geometry offsets, selected versus raw metadata, Field GT scoping and ROI behavior. Browser tests cover the fifth pipeline and existing PDF/Dataset workflows.

## Validation — 2026-09-23

- Full backend suite: 136 passed, including isolated local PostgreSQL. The two additional final-review cases cover the current leaf REC format for both batch adapters. Two existing dependency deprecation warnings remain.
- Ruff, frontend typecheck, ESLint and production build passed. Complete Playwright suite: 28 passed.
- The PDF failure was an outdated four-result assertion. The test now compares returned pipeline IDs against configuration, verifies every result succeeds and has metrics, and checks identical manual-crop hashes across all pipelines. The new Field GT browser test explicitly opens the field before editing.
- Local PostgreSQL upgraded to `0007_fields_roi_source`; Alembic found no schema drift. No migration 0008, environment change or production migration.
- Tracked and candidate files passed private-environment-value and token/private-key pattern scanning. `.env` remains ignored/untracked; local smoke helpers and outputs are excluded.
- Final real adapter smoke passed for both pipelines using one synthetic ROI (1000 × 350 PNG): 2 DET polygons → 2 REC results in order. Thai FT v2 selection reported V6 / `thai_ft_v2` at both stages, confidence 0.987436, Gateway durations 1170.37 + 417.61 ms. Benchmark retained V6/V5 baseline without `model`/`engine`, confidence 0.971055, durations 1087.00 + 384.32 ms. Both retained per-stage request IDs and `model-api-gateway` service metadata. These sample values validate integration, not accuracy or performance generally.
- The latest successful responses used `rec_text`/`rec_score` and omitted per-result `model`; fixtures retain the earlier confirmed stale model label to prevent routing regressions. No production database or deployment was changed.
