# Response mapping investigation

## Incident status

The clarified report is that the application may return an error and response mapping is suspected. No incident HTTP status/body, deployed SHA or failing synthetic input has been supplied. **The CDGS application-error root cause remains UNCONFIRMED.** No CDGS production calls, deployment, restart or credential changes were performed in this investigation.

The local investigation found a schema validation gap and fixed it. Numeric strings `"NaN"` and `"Infinity"` could pass through conversion into nonfinite polygon coordinates or `text_angle`. Subsequent strict JSON serialization would fail. The schema now uses Pydantic `FiniteFloat` for both fields and rejects them at conversion. There is no evidence connecting this malformed-native-output case to the reported incident.

## Reproduced before/after

These examples are deliberately invalid synthetic model output, expressed as Python diagnostics. They are not successful HTTP payloads.

```python
# Input coordinate fragment
{"box": [["NaN", 5], [20, 5], [20, 15], [0, 15]]}
# Before, convert() could produce a nonfinite Python float.
{"box": [[float("nan"), 5.0], [20.0, 5.0], [20.0, 15.0], [0.0, 15.0]]}
# After, convert() raises a validation error before constructing response data.
```

The HTTP failure envelopes stay safe. An unexpected invalid native result causes Single500 `INTERNAL_ERROR` or a Batch item error `MODEL_INFERENCE_FAILED`. The fix preserves valid Single/Batch data and never substitutes invented coordinates or OCR success.

## Correct response selection

Single selects `response.data.text` and `response.data.lines`. Batch selects a successful item's `result` using its original input index. Mixed failure items retain their indices and have `result=null`.

```python
single_data = single_response["data"]
items = batch_response["data"]["results"]
item = next(item for item in items if item["index"] == requested_input_index)
if item["status"] == "success":
    data = item["result"]
    text = data["text"]
    lines = data["lines"]
else:
    error = item["error"]
```

Keep the model's complete `text`. Multiple line entries can share a row, so joining all line texts with newlines changes content. A four-point polygon keeps its `[x,y]` points and order. `rotation`/`text_angle` describe model processing while the returned polygons already refer to original input pixels. A cropped Field has its own input frame, and a document consumer adds the crop offset once.

## Independently executed checks

- Full standalone67passed,0failed/errors/skipped. Seventeen new cases cover Thai/English multiline text, original/90/180/270 input orientation, Single/Batch equality, ordering, corrupt/empty items, finite coercion and safe HTTP handling of invalid native numbers. Four string-nonfinite cases failed before the schema fix.
- Actual Dockerfile Linux/Python3.12 build/start with verified pinned model,1CPU/1536MiB,no swap,read-only snapshot. All9application source hashes matched the candidate.
- Real HTTP inputs were original synthetic Thai/English, rotations90/180/270,7degree skew and blank. Six Single responses and seven Batch items including corrupt input passed exact equality of successful data objects. Twelve native calls were captured before conversion and their text/lines/polygons/confidence/rotation/angle matched API output exactly.
- Actual model line counts for those cases were2/2/1/2/2/0. The model returned rotation0 for these samples, with text angles including-0.44,-0.58 and-7.46degrees. The synthetic reader-doubled tests separately exercise nonzero rotation metadata. These checks establish mapping fidelity, with OCR accuracy remaining model-dependent.
- The existing OCRLab adapter consumed all six real Single payloads with ROI offset `(37,53)`, retained full text and applied that offset exactly once. Existing boundary clipping was accounted for independently. A whole Batch envelope and an error item were rejected as Single payloads. Adapter code was unchanged. Its existing focused suite passed46tests using isolated local fixtures.
- Kernel memory.peak was541859840bytes under1536MiB; OOM/max events0. This diagnostic run establishes behavior for the synthetic inputs and does not establish CDGS capacity.
- Ruff, pip check, diff and secret scans passed. The initial local capture harness needed a Python import-path correction before the accepted real-model run. Its failed attempt is excluded from passing results. Private synthetic captures and probe files remain outside Git.

A rendering failure has not been reproduced. The current evidence does not justify changing OCRLab response mapping or renderer behavior. PR18 was already merged, so this follow-up uses the focused `fix/openthai-box-contract` branch for separate review.

## Reproduce locally or on the existing service host

Use the existing service's private loopback endpoint and approved `OPENTHAI_API_KEY` in the client environment. Run from this independent directory with dependencies installed.

```sh
python scripts/verify_mapping_http.py --url http://127.0.0.1:8091 --output /private/path/synthetic-mapping.json
```

The script uses packaged/generated synthetic images, six Single requests and one Batch of seven. It checks index/error selection, complete data equality, dimensions, finite four-point polygons and blank output. The output file deliberately contains synthetic OCR responses for inspection. Console output contains only test counts. The runner restricts targets to loopback and rejects redirects.

## Owner follow-up

After review, the CDGS owner can update the existing OpenThai service from the focused fix commit using the current [in-place deployment procedure](CDGS_HANDOVER.md). Preserve service identity, private authentication, snapshot and limits. Run the synthetic response check and return the deployed source/image SHA, HTTP status, safe error code and request ID if the application still fails. Confirm the client uses the Single public route for OCRLab's current per-Field workflow. Public Batch deployment/mapping still requires owner confirmation. A successful local response cannot confirm recovery of an unobserved CDGS incident.
