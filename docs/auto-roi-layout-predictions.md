# Auto ROI layout-predictions integration

Auto ROI sends multipart `image` to the logical path `/api/v1/layout-predictions`.
`ModelGatewayClient` selects service `layout`, so its configured prefix applies.
For the CDGS `/paddle` deployment the resolved path is
`/paddle/api/v1/layout-predictions`.

The verified single-image response has `data` as a one-item array containing a
`boxes` array. Each box supplies a numeric four-value `coordinate` in input-image
pixels, a string `label`, and optional `score`. Only this explicit raw layout
shape is adapted. Empty boxes are valid. Multiple image results, malformed
containers, missing labels, nonfinite coordinates and reversed/zero-area boxes
fail with HTTP 502. Internal source paths are discarded.

The adapter supplies the existing ROI parser with `bbox`, `label` and `score`.
Existing text-class filtering, rounding, clipping to the uploaded/rendered page,
and the 1,000-region processing cap apply. Legacy object responses containing
`regions` or `text_lines` retain their existing parsing behavior. OCR pipelines
and their response normalizers are unchanged.

## Request parameter semantics

The request still forwards `auto_roi_mode` and `expand_text_rois`. Real CDGS tests
of all three modes with both expansion values returned HTTP 200 and identical
coordinates on one synthetic page. The accessible layout-model source uses
model inference directly, while the former document-layout pipeline implements
mode selection and expansion in its orchestrator.

Auto ROI therefore exposes text-class layout boxes from this endpoint. It does
not synthesize text-line detections or padding, and makes no claim that the
forwarded flags have the former pipeline effects. The frontend continues to
consume the same `regions[].roi` response and supports manual editing.

## Verification

The committed fixture is derived from a synthetic 1200×1600 page. Its internal
path and request metadata are replaced with synthetic placeholders. It contains
13 native boxes, including one table excluded by existing text-only filtering.
Tests cover every mode/expansion combination, valid empty output, malformed
responses, coordinate frame, rounding/clipping and existing legacy parsing.
