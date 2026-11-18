# Official model comparison

Sources checked2026-11-19; exact HF snapshots are pinned in `model-manifest.json` including per-file Git blob hashes and LFS SHA-256.

| Property | dots.ocr | dots.mocr |
|---|---|---|
|Official ID|`dots-studio/dots.ocr`|`dots-studio/dots.mocr`|
|Revision|`c0111ce6bc07803dbc267932ffef0ae3a51dc951`|`7c53434cd403d2e7f5f1d745eb2a2467a6473423`|
|Safetensors bytes, verified from pinned metadata/download|6,078,431,736|6,078,431,736|
|Architecture|DotsOCRForCausalLM, ~3B vision-language|DotsOCRForCausalLM, ~3B vision-language|
|Native artifacts|Layout JSON, HTML tables, LaTeX/Markdown|Document/graphics extensions advertised by upstream; layout prompt tested here|
|Measured runtime|Windows/PyTorch2.5.1+cu121, Transformers4.51.3, BF16, SDPA|Linux Docker/vLLM0.17.1, PyTorch2.10.0+cu129, Transformers4.57.6, BF16|
|Native Windows4.51.3|REAL MODEL PASS|BLOCKED: processor constructor gets multiple `chat_template` values|
|Linux/vLLM|Architecture supported; this model/runtime combination not benchmarked here|REAL MODEL PASS; inspect final results for resource/shutdown limitations|
|CPU-only inference|UNTESTED; CPU Docker start/auth only|vLLM profile requires CUDA; no CPU claim|

**Selection:** `dots.ocr` remains the default for the pinned native profile because actual Thai/English/layout/Single/Batch inference worked without FlashAttention or patching upstream code. `dots.mocr` is an explicitly separate Linux/vLLM alternative, validated on the same synthetic fixture set. Both models' output and limitations are documented rather than selecting on advertised scores. Measured latencies across these different runtimes are **not a controlled model-only speed comparison**. Neither proves quality on private/business documents.

Observed compatibility details: OCR AutoProcessor failed on Transformers4.56.1 (`video_processor` None), and worked on4.51.3 with `use_fast=False`. MOCR's newer processor expects the newer constructor;4.51.3 fails before inference. MOCR vision source also directly imports FlashAttention, absent from the native Windows environment; we did not inject a fake package or modify model files to bypass this. The tested Linux/vLLM profile uses its built-in model implementation and pinned native chat template. It does not use OCRLab or a CDGS Gateway.

The official repository describes the dots.ocr-1.5 → dots.mocr rebranding and graphics capabilities. Such source claims are distinguished from our chart-caption/Picture and formula tests; this API does not claim SVG chart reconstruction simply because the model advertises it.

## Licenses and attribution

HF cards declare MIT, and both snapshots additionally contain their named LICENSE AGREEMENT and NOTICE. The agreements state MIT precedence when inconsistent and supplemental conditions in other cases. Do not describe distribution as an unconditional MIT-only grant. No weights are redistributed in Git; operators download the exact official snapshot and retain its notices. Review those agreements for your intended use; this document does not resolve legal interpretation.

The official layout prompt was copied from the pinned OCR repository; attribution/license is included in this directory. No weights are trained or modified.

Primary sources:

- [Official OCR card](https://huggingface.co/dots-studio/dots.ocr/tree/c0111ce6bc07803dbc267932ffef0ae3a51dc951)
- [Official MOCR card](https://huggingface.co/dots-studio/dots.mocr/tree/7c53434cd403d2e7f5f1d745eb2a2467a6473423)
- [OCR agreement](https://huggingface.co/dots-studio/dots.ocr/blob/c0111ce6bc07803dbc267932ffef0ae3a51dc951/dots.ocr%20LICENSE%20AGREEMENT)
- [MOCR agreement](https://huggingface.co/dots-studio/dots.mocr/blob/7c53434cd403d2e7f5f1d745eb2a2467a6473423/dots.mocr%20LICENSE%20AGREEMENT)
- [Pinned prompt](https://github.com/studio-dots-ai/dots.ocr/blob/36d7248878f181c6257dc1cbd799ae940970444f/dots_ocr/utils/prompts.py)
- [Pinned coordinate post-processing](https://github.com/studio-dots-ai/dots.ocr/blob/36d7248878f181c6257dc1cbd799ae940970444f/dots_ocr/utils/layout_utils.py)
- [Official Docker profile](https://github.com/studio-dots-ai/dots.ocr/blob/36d7248878f181c6257dc1cbd799ae940970444f/docker/Dockerfile)
- [MOCR paper](https://arxiv.org/abs/2603.13032)
