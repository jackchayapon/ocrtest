# Actual synthetic feature matrix

REAL MODEL + REAL HTTP, both final profiles. Expected-marker checks are deliberately limited; they are not a private-document quality benchmark.

|Profile|Fixture|HTTP|Expected marker|Native categories|Out-of-frame boxes guarded|
|---|---|---:|---|---|---:|
|ocr-final|english|200|True|Text|0|
|ocr-final|thai|200|True|Text|0|
|ocr-final|mixed|200|True|Text,Text|0|
|ocr-final|english_jpeg|200|True|Text|0|
|ocr-final|english_webp|200|True|Text|0|
|ocr-final|crop|200|True|Text|0|
|ocr-final|rotated|200|True|Text,Text|0|
|ocr-final|skewed|200|True|Text,Text|0|
|ocr-final|blurred|200|True|Text,Text|0|
|ocr-final|blank|200|True|Picture|1|
|ocr-final|resolution_small|200|True|Text|0|
|ocr-final|resolution_medium|200|True|Text|0|
|ocr-final|resolution_large|200|True|Page-header|0|
|ocr-final|full_page|200|True|Section-header,Text,Text,Text,Text,Text,Text,Text,Text,Text,Text|0|
|ocr-final|table|200|True|Table|0|
|ocr-final|complex_table|200|True|Table|0|
|ocr-final|invoice|200|True|Text,Text,Text,Text|0|
|ocr-final|multicolumn|200|True|Section-header,Text,Text,Section-header,Text,Text|0|
|ocr-final|formula|200|True|Text,Formula,Formula|0|
|ocr-final|chart|200|True|Caption,Picture|0|
|ocr-final|corrupt|422|None||None|
|mocr-vllm-final|english|200|True|Text,Text|0|
|mocr-vllm-final|thai|200|True|Text,Text|0|
|mocr-vllm-final|mixed|200|True|Text,Text|0|
|mocr-vllm-final|english_jpeg|200|True|Text,Text|0|
|mocr-vllm-final|english_webp|200|True|Text,Text|0|
|mocr-vllm-final|crop|200|True|Page-header,Page-header|1|
|mocr-vllm-final|rotated|200|True|Text,Text|0|
|mocr-vllm-final|skewed|200|True|Text,Text|0|
|mocr-vllm-final|blurred|200|True|Text,Text|0|
|mocr-vllm-final|blank|200|True|Picture|1|
|mocr-vllm-final|resolution_small|200|True|Text|0|
|mocr-vllm-final|resolution_medium|200|True|Text|0|
|mocr-vllm-final|resolution_large|200|True|Text|0|
|mocr-vllm-final|full_page|200|True|Section-header,Text,Text,Text,Text,Text,Text,Text,Text,Text,Text|0|
|mocr-vllm-final|table|200|True|Table|0|
|mocr-vllm-final|complex_table|200|True|Table|0|
|mocr-vllm-final|invoice|200|True|Text,Text,Text,Text|0|
|mocr-vllm-final|multicolumn|200|True|Section-header,Text,Text,Section-header,Text,Text|0|
|mocr-vllm-final|formula|200|True|Title,Formula,Formula|0|
|mocr-vllm-final|chart|200|True|Caption,Picture|0|
|mocr-vllm-final|corrupt|422|None||None|

Source images/hashes/expected text: `tests/fixtures/manifest.json`. Complete responses: `benchmarks/<profile>/response-<fixture>.json`.

PNG/JPEG/WebP decoding and real inference were exercised; PDF is unsupported415. Corrupt input422 is the expected rejection, not a failed OCR result mapped as success. Tables/merged headings remain native HTML; chart captions/Picture are not numerical chart reconstruction. Formula output retains native LaTeX. Model reading order is retained, not independently corrected. Rotated/skewed boxes stay in the provided image's frame; no rotation angle is invented.

Blank is text-empty but can produce a hallucinated Picture box; `geometry_status` documents this. All finite usable mapped boxes are validated against image bounds. No confidence calibration or production capacity claim.
