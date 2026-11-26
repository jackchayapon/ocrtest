# Full-image GT / DET identity check

Opening the GT position check automatically loads the GT prefill rectangles and compares them with the selected pipeline. No separate initialization or check button is required. Changing pipeline automatically checks that pipeline.

The preview shows GT and pipeline images side by side. GT IDs, text, order and rectangles are fixed. Neither image allows drawing, moving, resizing, deleting or adding rectangles. Select two boxes on the **pipeline** side and swap their Field IDs. This exchanges the pipeline-box-to-GT-ID assignments only; all coordinates and GT references remain identical. Initially pipeline IDs follow the saved detector order. Red marks assignments that disagree with the reference geometry. The check updates automatically after a swap. Fields without rectangles remain present and cannot be assigned fabricated geometry.

The save API rejects changes to GT IDs, order, text or rectangles against the canonical GT references. Confirmations created by the earlier editable-GT implementation require reconfirmation before recalculation. Stored OCR output and detector order remain untouched; saved pipeline assignments determine evaluation order.

The frontend validates saved rectangle coordinates numerically, independent of JSON object key ordering (including PostgreSQL JSONB serialization), so reopening the editor restores saved Field IDs instead of reverting to detector order. The inspection entry point sits inside the full-image GT form. Its normal preview displays the canonical GT DET rectangles in a light color; selecting a Sub-field focuses its corresponding rectangle, and clicking a rectangle selects that Sub-field. The form shows the saved coordinates. Missing GT coordinates remain unavailable rather than borrowing Pipeline geometry.

The paired preview uses one shared toolbar for zoom, actual size, fit/reset and Field-label visibility. Both viewers share the same image-space center and scale, including wheel zoom and background dragging from either side. Drag blank image space to pan both views; click a Field box to select it without moving its rectangle. Document previews now use combined select/background-pan navigation by default, with drawing still a separate explicit tool.

Pipeline readiness is grouped into passed and needs-review panels. On wide screens, the two previews and Field-ID editor occupy three columns; smaller screens stack them. Tags identify unchanged IDs, changed IDs (relative to original detector order), and locked empty placeholders. After the last required confirmation in a pending calculation, a separate popup offers to calculate scores immediately. Confirmed text-only or missing-box cases are described as confirmed limitations, not as complete geometric matches.

Both ROI and full-image calculation show a blocking loading screen with elapsed time and completed-step progress. ROI has save/evaluate steps; full-image adds alignment review. The synchronous evaluation endpoint does not publish within-evaluation progress, so the bar remains at the last completed step until its response arrives. It does not simulate a percentage of characters compared. Errors dismiss the loading screen and preserve the editor for retry.

When a pipeline has fewer DET boxes than the GT and GT geometry is available, initialization matches geometry to locate gaps instead of assigning by index. Each missing reference gets a yellow, dashed, locked placeholder on the pipeline preview at the GT position. Its label explains that it exists only for alignment, not as a detector result. It is excluded from swap controls and raw OCR boxes. A 25-field GT with 24 matching detections therefore has 25 comparison slots, including an empty slot at the missing position. Subsequent IDs retain their GT numbers. Saved placeholders have empty text and no confidence; line CER/WER counts missing text as deletions. The API rejects attempts to assign an actual box into a locked missing slot. Extra OCR detections are still retained and counted; they are never discarded to force equal counts. Without GT geometry the system cannot infer the location of a missing box.

Confirming persists the correspondence per run in `test_cases.full_image_alignment`. Normal GT evaluation uses it for prediction grouping, CER/WER, line confidence, results and exports. Missing predictions remain empty, extras count as insertions, and raw OCR text is untouched. Editing the underlying GT requires reconfirmation. A fresh OCR run does not inherit old assignments. A pipeline whose DET text omits characters present in its full OCR output cannot confirm correspondence, avoiding silent loss of text from scoring.

GT coordinates come from saved prefill metadata or the original job checkpoint, never from the pipeline being tested. New direct and incremental runs retain compact prefill text/rectangles. Older checkpoints that discarded those rectangles cannot support a geometric check; the UI explicitly reports missing GT geometry and preserves the existing text comparison.

The additive migration from the initial implementation remains required:

```powershell
cd backend
.venv/Scripts/python.exe -m alembic upgrade head
```

The old experimental inspector and its button have been removed from the evaluation screen. The GT page is the only alignment editor.

Full-image calculation first saves GT and checks all latest successful pipelines using `/alignment-review`. Complete matching geometry passes automatically. A mismatch opens the GT alignment dialog on the first failing pipeline and prevents evaluation; the dialog displays green checks for ready pipelines and red statuses for those requiring work. Calculation sends `require_spatial_review` so the backend rechecks immediately before updating scores.

Missing/extra boxes require explicit confirmation even when automatic matching is unambiguous. Confirmed placeholders remain empty for scoring. Missing GT or DET geometry is not labelled a geometric match: the user must explicitly confirm text-only evaluation of the original OCR output. Such confirmation is labelled as text-only in the pipeline status. Changes to GT or old correspondence invalidate previous confirmation.
