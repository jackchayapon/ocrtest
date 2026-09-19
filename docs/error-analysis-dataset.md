# ROI, error analysis and Dataset Builder

The existing workspace and Gateway contracts are unchanged. No new environment
variables or external services are required. Apply the additive migration with
`cd backend` then `.venv\Scripts\python.exe -m alembic upgrade head` against your
chosen development database. Revision `0006_ocr_error_events` creates only the
error-event table and indexes; it does not rewrite historical metrics or images.

## ROI

Drawing, dragging or resizing a region marks it as editing. Auto Detect returns
suggestions only; choosing one marks it as suggested and makes it editable.
Click **ยืนยัน ROI** before saving or running a selected region. Further edits
require confirmation again. Saved historical ROIs are treated as confirmed.
Coordinates stay in the original image/PDF page pixel grid. Bounds, pan and zoom
use the existing viewer transforms. There is no additional browser crop.

Mint and Hutch Crop share the canonical backend crop of the final ROI. Hutch Full
continues to ignore ROI and sends the full image/selected PDF page. Without an ROI,
the existing full-page benchmark remains available. An explicit saved ROI is
required for Dataset eligibility (including an explicit whole-page rectangle).
Changing a saved ROI before OCR invalidates Ground Truth confirmation. After OCR,
the existing API requires a new test case to preserve historical predictions.

## Error analysis

`/analytics/errors` shows aggregated substitutions, deletions and insertions with
case/document links and category metadata. API:

- `GET /api/analytics/errors`: `pipeline`, `category`, `error_type`,
  `error_level=char|word`, `text_kind=raw|final`, `test_case_id`, `document`,
  `limit` (1–200, default 50), `offset`.
- `POST /api/test-cases/{id}/errors/recompute`: explicitly recalculates metrics
  and events for this case using saved predictions and current GT, without OCR.

Normalization remains NFC plus whitespace collapse/trim. Alignment uses the same
unit-cost Levenshtein recurrence as existing CER/WER, with linear-space Hirschberg
traceback. Ties deterministically choose the leftmost split, then diagonal,
deletion, insertion in the small traceback. Different optimal alignments can
attribute an ambiguous error differently; total edit counts still match distance.
Positions are zero-based normalized Unicode code points or whitespace tokens, not
raw string offsets or grapheme clusters. Missing units/positions are null.
Thai text without whitespace is one WER token; CER remains preferable for Thai.
Empty GT with nonempty prediction keeps the existing undefined CER/WER while
showing insertion events. Neither spelling nor punctuation is corrected.

Events are replaced transactionally when GT is saved/confirmed or OCR runs. Raw
and final predictions have separate events. Aggregation uses the latest eligible
run per case/pipeline, like Matrix; reruns do not double-weight a case. Archived
runs are excluded. Counts refer to occurrences, not distinct documents. Each group
includes the first 20 case links and its total case count; filter by document or
case for narrower inspection. Categories are joined from TestCase, never copied
into error rows or sent to inference. Historical missing events are not silently
treated as proof of perfect OCR: use the per-case recompute button on the analysis
view (also linked from Test Detail). No production backfill runs automatically.

## Dataset export

`/dataset` lists saved cases with a non-null ROI, non-null GT and `confirmed`
status. Selection is local UI state. Editing GT removes eligibility until it is
confirmed again. Empty but explicitly confirmed GT is a valid empty label.

- `GET /api/dataset/samples`: `category`, `document`, `limit`, `offset`.
- `POST /api/dataset/export`: `{"test_case_ids":["<UUID>"]}`. Up to 200 unique
  cases and 512 MiB of encoded images per export. Errors reject the whole export;
  missing files/cases return 404 and ineligible selections return 422.

```text
dataset/
  images/000001.png
  images/000002.png
  label.txt
```

`label.txt` is UTF-8, one sample per line:
`images/000001.png<TAB>confirmed ground truth<LF>`.
Labels preserve raw confirmed GT. Escape backslash as `\\`, tab as `\t`, carriage
return as `\r` and newline as `\n`. Consumers should split once on the actual tab,
then decode these four backslash escapes in a **single pass** (do not use a generic
Unicode-escape decoder on Thai). No OCR predictions or benchmark metrics are labels.

Cases sort by UUID regardless of selection order. ZIP timestamps and entry names
are fixed, making unchanged inputs reproducible. Source documents/page numbers,
ROIs, source hashes and update timestamps remain in the database/list API for
traceability. Images are rendered at the stored PDF DPI or original raster size,
then cropped through ImageService into lossless PNG. StorageService supplies the
source; no permanent duplicate crops are created. ZIPs spool to temporary storage
above 16 MiB and close after streaming or failure. User filenames never become
ZIP paths and the API accepts UUIDs only.

## Future pipelines

Run/filter schemas, config ordering, logs and new views accept iterable pipeline
IDs. The registered adapter declares `requires_crop` and its engine; no fourth
adapter or invented inference contract is provided. Unknown configured pipelines
return an isolated `ADAPTER_NOT_CONFIGURED` result and never make HTTP calls.
Once a verified contract exists, register an adapter in PipelineManager, add its
config and implement its connection/auth handling where required; the existing
run/GT/metric/error-event path can then be reused. Gateway-specific status/model
names and the current three adapters remain intentionally explicit.
