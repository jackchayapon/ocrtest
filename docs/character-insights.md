# Character Error Insights

Evaluation shows errors for the latest non-archived run of each pipeline on one test case/page. No OCR rerun, new database tables, or persisted alignment streams are involved.

## Walkthrough

1. Open Ground Truth & Evaluation. Highlight starts enabled here only; Deep detail remains optional. Each pipeline has an independent Highlight toggle.
2. Under a field's metrics, expand **Character Error Summary**. Closed summaries use already-loaded spans for counts and issue no detail requests.
3. Select a character to inspect GT/OCR excerpts, error type and field identity. Combining marks use a dotted circle; actual code points are unchanged.
4. Select **Field Crop** to load the original crop endpoint for that document, ROI and PDF page. Zoom, Fit, mouse drag, keyboard arrows and full-page view are available. Full-page view outlines the field, not an invented character box. Missing source files show an error.
5. **Export Evaluation Report** downloads every latest non-archived pipeline in the current case/page, including pipelines hidden by the UI filter.
6. History **View Errors** opens only the clicked pipeline's detail. Escape closes the top dialog and returns focus. No details or crops are fetched for unclicked rows.

The comparison table uses 280px pipeline columns and one bounded scroll region with sticky headers and GT column. Text panes no longer have separate fixed-height scroll regions. Wheel scrolling can chain to the page at the boundary. Image-viewer wheel events are consumed only while moving the image or during Ctrl/Cmd zoom.

## Counting and eligibility

- Reuses canonical align_errors, NFC and whitespace normalization. CER remains Unicode code-point based, including normalized spaces.
- Current main uses Thai newmm word tokenization; this feature does not change WER.
- Substitutions/deletions belong to the GT character; insertions belong to the extra OCR character. A substitution is counted once.
- Totals equal canonical character edits. Aggregates divide total edits by total GT units; field percentages are not averaged.
- Only the selected evaluation mode contributes. Whole-document and field results are never added together.
- Unconfirmed, changed, failed or unavailable evaluations are explicit. Legacy cases require confirmed GT and OCR evidence.
- Single-line attribution is supported. Multiline attribution is unavailable because normalized whitespace does not retain reliable boundaries.
- Original ROI coordinates provide field/page geometry, not precise character locations.

Rules version: nfc-whitespace-codepoint-v1/wer-newmm-v1.

## Read-only APIs

- GET /api/test-cases/{id}/error-summary?pipeline_id=...
  Optional field_id, mode=per_field|whole_document, and a one-code-point character filter.
  Four scoped projections; no Gateway JSON, boxes, diagnostics or ORM relationship cascade.
  Default detail contains small excerpts and at most 50 events per scope.
- GET /api/test-cases/{id}/evaluation-report?mode=...
  Explicit-click ZIP, Cache-Control: private, no-store.
- History keeps view=summary&latest=true, with opt-in compact=true only on History. Existing consumers, including Matrix, retain the original summary shape. Compact History contains no OCR/GT strings, geometry or alignment JSON.

Catalog caching and Dataset Export are unchanged. No environment variable or migration is required.

## ZIP format

- summary.json: document/page/case, rules version, timestamp, run status, confidence, timing and aggregate metrics/statistics.
- pipeline_results.csv: field/document OCR, confirmed GT, metrics and identities for all latest runs.
- character_errors.csv: code point/name, edit counts and confusion pairs.
- error_details.json: exact text, GT, ROI, eligibility and canonical events.
- README.txt: scope and counting/encoding rules.

JSON preserves exact strings. CSV is UTF-8 with BOM; formula-like cells receive an apostrophe prefix. Archive names are fixed. No raw Gateway envelopes, credentials or images. Missing/outdated metrics are not fabricated.

Bounds: 100 pipelines, 2,000 prediction fields, 200,000 input characters overall, 40,000 normalized characters per alignment, 16 million unmatched alignment cells and 16 MiB serialized report. Oversized requests return 413. Export covers one case/page, not all PDF pages.

## Validation and transfer evidence

See [character-insights-validation.md](character-insights-validation.md). Measurements use isolated local PostgreSQL and estimate fetched UTF-8 DBAPI values. They are **not** Neon billing reductions.
