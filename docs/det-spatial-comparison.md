# Full-image DET position and reading-order inspection

Open a full-image case's existing evaluation screen and choose **ตรวจตำแหน่งและลำดับ DET**.

1. Choose a successful pipeline with stored DET boxes as the reference. Its OCR text is a draft, not verified GT.
2. Check the image and edit reference text, move fields up/down, resize selected boxes, remove boxes, or draw missing boxes.
3. Select the pipeline to inspect. Confirm the reference GT only after checking it against the image.
4. Run the inspection. Select reference rows to highlight corresponding DET boxes. For uncertain matches, open the mapping editor, choose a reference or mark a detection as extra, then inspect again.
5. Download the JSON report to retain the reference, manual mappings and results. Drafts are in component memory only; closing the inspector or changing the reference pipeline discards them.

This is a read-only experimental inspection. It does not update canonical layout, saved GT, benchmark scores, or OCR jobs. The shared reference permits comparison of different pipeline outputs against the same text. It is separate from per-pipeline GT editing.

## Matching and order

The server loads the selected run from the current case, validates reference coordinates against the image/page bounds, and uses stored absolute image coordinates. It does not apply ROI offsets a second time.

A detection is a candidate for a reference when their intersection covers at least 50% of the smaller axis-aligned bounding rectangle. Text similarity is not used. These are candidate matches, not guaranteed segmentation correctness; rotated polygons and overlapping references can be ambiguous.

- One candidate: assign the detection to that reference.
- Multiple detections assigned to one reference: report a split and join their text in stored order using spaces.
- Multiple candidate references for a detection: mark ambiguous/possibly merged. Do not guess how to split its text or compute an overall spatial score until resolved.
- No candidate: report an extra detection. Unmatched references are missing.
- Manual assignments are explicit in the report and can affect scores.

Order inversions count detection pairs whose stored order disagrees with reference order. Zero inversions is not a claim of complete agreement when references/detections are missing or unresolved. Some adapters already sort DET results before persistence: this tool reports **stored OCR order**, not reconstructed original model emission order.

## Scores

Scores are available only after the user confirms the draft reference as GT. Both use existing CER/WER normalization and tokenization:

- Stored-order score compares saved `final_text` to the joined reference text.
- Spatial score joins matched text in reference order, retains empty missing references, and appends extra detection text so it is not silently dropped. This is a diagnostic comparison, not a replacement benchmark score.
- Each resolved reference also has a local score; unresolved references do not.
- Without geometry, only the stored full-text score is available. No positional score/order agreement is claimed.

## API

`POST /api/test-cases/{case_id}/spatial-comparison` accepts a run UUID, up to 128 reference entries (`id`, `roi`, `text`), optional detection overrides (`box_id`, `reference_id` or null), and `confirmed_gt`.

The response includes reference rows, match candidates, manual/automatic match status, missing/extra/ambiguous counts, inversions, and the two metric sets. It performs no writes and no upstream OCR requests. The frontend obtains detection IDs from saved field ID plus original box-array index.

Validation: `backend/tests/test_spatial_comparison.py` covers geometric matching, inversions, split/merge ambiguity, missing/extra boxes, lack of geometry, input validation and API non-mutation. `frontend/tests/spatial-comparison.spec.ts` covers the inspector, reference reorder/edit, GT confirmation and returning to the original evaluation screen.
