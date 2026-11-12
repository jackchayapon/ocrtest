# Verified model runtime

Reviewed revision `39fa41bdd49f067ba41b1d9de79c06ab506d67d4` on 13 November 2026.

- Detector PP-OCRv6-tiny, 428K parameters, approximately 1.8 MB ONNX.
- iApp Thai/English CTC recognizer, 587K parameters, approximately 2.4 MB ONNX. Input `[N,3,48,W]`, output `[N,W/8,530]` softmax.
- `LineOCR(model_dir, threads=1, runtime={"backend":"onnxruntime"})` loads two networks once. The service chooses ONNX Runtime explicitly for a reproducible CPU dependency set.
- `read` accepts a path, bytes, BGR ndarray or PIL image. The API validates PNG/JPEG and supplies an owned RGB PIL image. EXIF orientation is retained as stored pixel coordinates. The runtime handles orientation and deskew itself.
- `text` is a string assembled by the runtime in reading order. Multiple lines on the same row may be space-joined. Preserve this string and `lines` ordering instead of rebuilding text by joining every line with a newline.
- Each line has string `text`, Python float `confidence`, integer `row`, and a four-point polygon `box` of float coordinates. Optional native NumPy arrays/scalars are converted safely by the HTTP boundary.
- Coordinates are absolute pixels in the caller's original image. `_apply(back, boxes[i])` maps orientation/deskew coordinates back once. OCRLab adds the Field ROI offset once.
- Confidence is the recognizer's mean probability of retained greedy CTC character frames, rounded to four decimals. It ranges from zero to one and is model confidence rather than calibrated page accuracy. Aggregate API confidence remains null.
- Small line-shaped images with no detector boxes may use the runtime's whole-image line-recognition fallback. The service preserves actual returned geometry.
- Blank 780×250 test images returned `text=""`, `lines=[]` in real inference. Other noisy/short inputs may be filtered or recognized according to the pinned config, including `min_chars=2`, `drop_below=.8`. The API adds no OCR heuristic.
- Corrupted images are rejected before inference. PNG/JPEG formats, dimensions, pixel count and decoder errors are validated.

The model card estimates approximately 450 MB per worker. Runtime comments describe higher long-running OpenVINO shape-cache usage. That estimate requires workload-specific measurement. This service starts one process, one inference slot and one native thread. A measured smoke workload is recorded in the integration verification report.

The model card declares Apache-2.0. Preserve upstream NOTICE, attribution, license notices and modification notices when redistributing. The repository provisions the original runtime and weights at installation time. The standalone API wrapper is maintained separately.

The upstream `SHA256SUMS` contains a stale README digest in this revision. Runtime/weights/configuration matched its manifest. The reviewed README has SHA256 `4738dea47f1d31454fbb6632460560927725388e70026137fa0f162c71e7329e`. Provisioning additionally checks the committed lock manifest for all ten files. A mismatch stops provisioning/startup.

Sources follow.

- [Pinned model card](https://huggingface.co/iapp/OpenThai2.0-OCR-Text/blob/39fa41bdd49f067ba41b1d9de79c06ab506d67d4/README.md)
- [Pinned runtime, LineOCR.read and coordinate mapping](https://huggingface.co/iapp/OpenThai2.0-OCR-Text/blob/39fa41bdd49f067ba41b1d9de79c06ab506d67d4/runtime/line_engine.py)
- [Pinned NOTICE](https://huggingface.co/iapp/OpenThai2.0-OCR-Text/blob/39fa41bdd49f067ba41b1d9de79c06ab506d67d4/NOTICE)
