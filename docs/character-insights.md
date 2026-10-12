# Character Error Insights

Evaluation shows errors for the latest non-archived run of each pipeline on one test case/page. No OCR rerun, new database tables, or persisted alignment streams are involved.

## Walkthrough

1. Open Ground Truth & Evaluation. Highlight starts enabled here only; Deep detail remains optional. Each pipeline has an independent Highlight toggle.
2. Under a field's metrics, expand **สรุปข้อผิดพลาดในการอ่านตัวอักษร**. Closed summaries use already-loaded spans for counts and issue no detail requests.
3. Select a character to inspect GT/OCR excerpts, error type and field identity. Combining marks use a dotted circle; actual code points are unchanged.
4. Select **Field Crop** to load the original crop endpoint for that document, ROI and PDF page. Zoom, Fit, mouse drag, keyboard arrows and full-page view are available. Full-page view outlines the field, not an invented character box. Missing source files show an error.
5. **ส่งออก Excel (.xlsx)** downloads the visible pipelines and selected fields in their displayed order, in the current mode/case/page. **ตัวเลือกขั้นสูง → ส่งออกรายงาน ZIP (ทุก Pipeline)** retains the all-latest-pipelines export, including hidden pipelines.
6. History **ดูข้อผิดพลาด** opens only the clicked pipeline's detail. Escape closes the top dialog and returns focus. No details or crops are fetched for unclicked rows.

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


## Single-sheet Excel and Thai explanations

POST /api/test-cases/{id}/evaluation-excel accepts mode, ordered pipeline_ids,
matching run_ids, ordered field_ids (empty for whole-document), and the saved
case updated_at as revision. Unknown/duplicate/foreign IDs are rejected; changed
revision/latest run returns 409. The server reads saved OCR/confirmed GT and
canonical alignment, not client predictions. No Gateway calls or database writes.

OCRLab_Evaluation.xlsx has exactly one sheet, ผลการประเมิน OCR:
document/case/page/mode/export time, field/document GT and OCR rows, Thai
substitution/insertion/deletion explanations, CER/WER/Exact Match/confidence and
explicit state, followed by weighted pipeline totals. Ratios are stored as
numbers with percentage formatting. Thai tone marks use a dotted circle only
for display; NFC, code-point CER and Thai newmm WER remain unchanged.

Successful child fields remain eligible even when their parent run fails.
Failed/missing fields retain confirmed GT where available and have blank scores;
partial totals include only eligible fields and disclose evaluated/total counts.
Whole-document evaluation still requires a successful complete run.

All strings are literal cells, including leading = + - @. No formulas, external
links, images or vendor responses. Wrap text, Tahoma, frozen headers/GT and
filters are applied. Oversized/illegal Excel text returns a clear error, never
silent truncation; use ZIP instead. Limits include 32,767 UTF-16 units per cell,
10,000 rows and 16 MiB output/text. Workbook data is verified with openpyxl;
native Microsoft Excel rendering has not been independently tested.
