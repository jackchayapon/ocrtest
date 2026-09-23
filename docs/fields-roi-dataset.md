# Field Ground Truth, ROI origins and Dataset export

This additive change uses the existing normalized PipelineRun boxes, metrics/alignment, source-coordinate ROI and StorageService. No Gateway endpoint, credentials, deployment configuration or production data migration is changed.

## Data and lifecycle

Alembic `0007_fields_roi_source` follows `0006_ocr_error_events`. It adds `test_cases.roi_source` (default `none`) and `ocr_fields`. Each UUID field belongs to one PipelineRun, which belongs to one TestCase. Unique `(pipeline_run_id, field_index)` identifies the normalized box snapshot: geometry, OCR text, recognition confidence, raw/normalized GT, confirmed timestamp and evaluation JSON. Deleting a run cascades its fields.

New successful runs generate fields from normalized boxes containing text; no combined-text splitting, semantic classification or cross-pipeline GT matching occurs. A rerun gets new field IDs. Historical results without field records remain readable with whole-document GT; no automatic GT backfill is attempted.

Field mode is the default Inspector mode. Select a field to highlight its existing OCR overlay; selecting a box selects its field. The list scrolls and field details collapse. Check calculates a preview without a DB write. Confirm persists that field only and replaces its evaluation snapshot, so repeated checks/confirmation never append duplicate events. Editing invalidates the preview until Check is pressed again.

Whole-document/ROI GT, its metrics and existing Error Analysis/Matrix semantics are unchanged. Field summaries appear separately for each PipelineRun in the Inspector; field confirmation does not confirm whole-document GT or make a Dataset sample eligible. Field error events are inside the field evaluation, separate from whole-GT `ocr_error_events`.

## API

Under `/api/test-cases/{case_id}/runs/{run_id}/fields`:

- `GET /`: list existing fields (actual route has no trailing slash requirement).
- `POST /{field_id}/check`: `{ "ground_truth_raw": "..." }`; returns preview metrics, events and aligned spans.
- `PUT /{field_id}/ground-truth`: `{ "ground_truth_raw": "...", "confirmed": true }`; saves/replaces confirmation. `confirmed=false` saves a draft without evaluation.

Every operation verifies case/run/field ownership. Existing test-case create/update and ROI update accept `roi_source: auto|manual|none`; auto/manual require an ROI. Coordinates/source cannot be changed on an already-tested case: the UI creates another test case to preserve the old results. Serialized runs add `fields` and `field_summary`.

## Metrics and red diff

The existing Unicode NFC, trimmed/collapsed whitespace normalization and whitespace WER tokenizer are reused unchanged. The existing alignment supplies substitution, insertion and deletion events. Red underlined OCR units represent substitutions/insertions; `⟦ขาด: X⟧` explicitly marks a missing GT character. Labels and tooltips supplement color.

- Aggregate CER = sum(character edit operations in confirmed fields) / sum(normalized GT characters).
- Aggregate WER = sum(word edit operations in confirmed fields) / sum(normalized GT whitespace tokens).
- Aggregate Exact Match = every included confirmed field matches.

Unconfirmed fields are excluded. No confirmed fields means null metrics. Zero GT denominator follows existing semantics: zero errors gives 0, otherwise the rate is null. WER has the same Thai whitespace-tokenization limitation as before.

## Auto and Manual ROI

Auto Detect remains explicit. Suggestions remain visible when selecting, moving, resizing or confirming one. Normal/hover/active suggestions have separate styles; the active ROI has edit handles. Manual drawing retains Auto suggestions and provides a button to restore the last manual region. Suggestions and the last manual ROI are remembered separately per PDF page for the current workspace session (not across reloads).

ROI origin is explicit and never inferred from dimensions. Moving/resizing an Auto suggestion retains `auto`; drawing a new region sets `manual`. Original source/page coordinates and backend canonical lossless PNG encoding remain authoritative.

| Active source | Mint / Hutch Crop / Benchmark | Hutch Full |
|---|---|---|
| auto | final selected ROI crop | full selected page/image |
| manual | final manual crop | same canonical crop, created inside adapter |
| none / historical unknown | existing ROI crop if supplied, otherwise full image | full selected page/image |

Hutch uses the same Paddle request with explicit `1.7 / 0.25 / 0.6` in both strategies. Mint custom OCR and Benchmark DET `/api/v1/text-detection-batches?version=6` → REC `/api/v1/text-recognition-batches?version=5` are unchanged. Benchmark still has no `model` or `engine` query.

## Dataset: reproduced failure and recovery

Before changing code, the production sample listing returned an eligible confirmed-GT record, but its source image/crop returned 404 and export returned 404 `Stored image is unavailable`. The proven cause is a database record whose source file is missing from local storage. ZIP encoding and labels were not the cause. This inspection does not establish why Railway lost the file or verify its volume configuration.

Sample listing now exposes `source_available`. Unavailable samples cannot be selected; the UI explains the missing original. Export preflights every source and catches a missing-file race, returning 409 with the affected test-case ID and recovery advice. The selection table stays visible on export errors. No partial ZIP, fake crop, OCR-derived label or empty replacement file is generated.

Existing exports are unchanged:

```text
dataset/
  images/000001.png
  images/000002.png
  label.txt
```

`label.txt` is UTF-8 escaped TSV: `images/000001.png<TAB>confirmed whole-GT<LF>`. Backslash, tab, newline and CR use reversible escapes. Images are cropped from the original stored image/rendered PDF page using final source ROI, never browser screenshots. OCR predictions, CER/WER/confidence/latency are never labels. Generated filenames and StorageService path validation prevent traversal.

Missing production originals require restoring files from a backup, or re-uploading and confirming new samples. Persistent storage/mount verification is an operator task; no deployment configuration was changed. No new environment variable is required.

## Final local validation (2026-09-22)

- Complete backend suite with explicit local `TEST_DATABASE_URL`: **126 passed**, including PostgreSQL; Ruff passed. Two existing Starlette/httpx/AnyIO deprecation warnings remain.
- Frontend `npm run typecheck`, `npm run lint`, `npm run build`: passed.
- Complete Playwright suite against production build on port 3100 and test backend on port 8100: **27 passed (40.1 seconds)**. Upstream HTTP is fixture-backed; this is separate from real Gateway smoke checks.
- Local API health and frontend HTTP: 200.
- Alembic upgrade/head and drift check: `0007_fields_roi_source`, no new upgrade operations. Also created a clean local PostgreSQL database at 0006, inserted a historical confirmed-GT case, upgraded to 0007 and verified the old record/GT/status survived with `roi_source=none`; drift check passed.
- `git diff --check`: passed. Checked 161 tracked/new nonignored files against private credentials without printing values; no matches. Credential-signature scan found no matches. `.env` remains ignored and untracked.
- Diff review: Mint/Hutch Crop/Benchmark adapters, metrics normalization, Dataset label repository, Gateway authentication, environment template, Docker and Next configuration remain unchanged. DocumentViewer changes are limited to ROI-origin callbacks, overlay ordering, active labels and overlapping-suggestion click handling; existing coordinate/zoom/pan code is retained and covered by the full suite.

Changed file groups: backend field repository/service/model/routes/schema/serializers, explicit ROI routing and crop diagnostics, Dataset/Storage availability; frontend FieldGroundTruth, TestingWorkspace, DocumentViewer/TestRegionLayer/AutoROIOverlay, CropDebugPanel, Dataset/settings pages, API/types; backend and Playwright regressions; README and flow/Benchmark/this documentation. No commit, push, deployment or production migration was performed.

### Reviewed file inventory

Real Gateway smoke using a synthetic English/Thai image also passed: Auto ROI returned two suggestions; Mint/Hutch Crop/Benchmark received the same 407×41 Auto crop; Hutch Full Auto received the full 1000×500 image. All four manual runs succeeded with the same 800×200 canonical input SHA-256. Credentials remained server-side; no production records/settings were modified. The temporary `.runtime/fields_real_smoke.py` helper was removed after testing. UI interactions were verified by the separate complete Playwright suite above.

Backend (13):

- `backend/alembic/versions/0007_fields_roi_source.py`
- `backend/app/api/routes/test_cases.py`
- `backend/app/db/models.py`
- `backend/app/pipelines/base.py`
- `backend/app/pipelines/hutch_full.py`
- `backend/app/repositories/field_repository.py`
- `backend/app/schemas/contracts.py`
- `backend/app/services/dataset_service.py`
- `backend/app/services/field_service.py`
- `backend/app/services/pipeline_manager.py`
- `backend/app/services/serializers.py`
- `backend/app/services/storage_service.py`
- `backend/app/services/test_case_service.py`

Frontend (10):

- `frontend/app/dataset/page.tsx`
- `frontend/app/settings/pipelines/page.tsx`
- `frontend/components/AutoROIOverlay.tsx`
- `frontend/components/CropDebugPanel.tsx`
- `frontend/components/DocumentViewer.tsx`
- `frontend/components/FieldGroundTruth.tsx`
- `frontend/components/TestRegionLayer.tsx`
- `frontend/components/TestingWorkspace.tsx`
- `frontend/lib/api.ts`
- `frontend/types/index.ts`

Tests (11):

- `backend/tests/test_batch_logs_delete.py`
- `backend/tests/test_error_analysis_dataset.py`
- `backend/tests/test_fields_roi.py`
- `backend/tests/upstream_fixture.py`
- `frontend/tests/batch-review.spec.ts`
- `frontend/tests/benchmark.spec.ts`
- `frontend/tests/console.spec.ts`
- `frontend/tests/dataset-errors.spec.ts`
- `frontend/tests/fields-roi.spec.ts`
- `frontend/tests/pdf.spec.ts`
- `frontend/tests/workflow.spec.ts`

Documentation (4):

- `README.md`
- `docs/benchmark-pipeline.md`
- `docs/fields-roi-dataset.md`
- `docs/flow.md`
