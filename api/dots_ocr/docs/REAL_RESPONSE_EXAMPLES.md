# Actual response examples

All examples are from the final local real-model/real-HTTP runs on committed synthetic images. No mock or private document output. Full versioned bodies and metadata are linked below; native_output is retained in those files.

## Single English

[Complete actual response](../benchmarks/ocr-final/response-english.json)

```json
{
  "data": {
    "schema_version": "1.0",
    "text": "Document 123\nHello world",
    "native_output": "[{\"bbox\": [29, 40, 207, 110], \"category\": \"Text\", \"text\": \"Document 123\\nHello world\"}]<|endofassistant|>",
    "elements": [
      {
        "index": 0,
        "category": "Text",
        "text": "Document 123\nHello world",
        "confidence": null,
        "native_bbox": [
          29.0,
          40.0,
          207.0,
          110.0
        ],
        "bbox": [
          28.571428571428573,
          39.285714285714285,
          203.9408866995074,
          108.03571428571428
        ],
        "geometry_status": "valid"
      }
    ],
    "tables": [],
    "image": {
      "width": 800,
      "height": 220
    },
    "model_image": {
      "width": 812,
      "height": 224
    },
    "coordinate_frame": "input_image_pixels",
    "reading_order": "model_sequence",
    "confidence": null
  },
  "meta": {
    "api_version": "v1",
    "request_id": "f5f29b48abc14fdcb24ee9e92370c6ec",
    "model": "dots-studio/dots.ocr",
    "revision": "c0111ce6bc07803dbc267932ffef0ae3a51dc951",
    "backend": "transformers",
    "device": "cuda",
    "dtype": "bfloat16",
    "duration_ms": 2141.0
  }
}
```

## Two-image Batch

[Complete actual response](../benchmarks/ocr-final/response-batch2.json)

```json
{
  "data": {
    "results": [
      {
        "index": 0,
        "status": "success",
        "result": {
          "schema_version": "1.0",
          "text": "Document 123\nHello world",
          "native_output": "[{\"bbox\": [29, 40, 207, 110], \"category\": \"Text\", \"text\": \"Document 123\\nHello world\"}]<|endofassistant|>",
          "elements": [
            {
              "index": 0,
              "category": "Text",
              "text": "Document 123\nHello world",
              "confidence": null,
              "native_bbox": [
                29.0,
                40.0,
                207.0,
                110.0
              ],
              "bbox": [
                28.571428571428573,
                39.285714285714285,
                203.9408866995074,
                108.03571428571428
              ],
              "geometry_status": "valid"
            }
          ],
          "tables": [],
          "image": {
            "width": 800,
            "height": 220
          },
          "model_image": {
            "width": 812,
            "height": 224
          },
          "coordinate_frame": "input_image_pixels",
          "reading_order": "model_sequence",
          "confidence": null
        },
        "error": null,
        "duration_ms": 2406.0
      },
      {
        "index": 1,
        "status": "success",
        "result": {
          "schema_version": "1.0",
          "text": "ภาษาไทย ทดสอบเอกสาร\nกรุงเทพมหานคร 123",
          "native_output": "[{\"bbox\": [29, 39, 322, 112], \"category\": \"Text\", \"text\": \"ภาษาไทย ทดสอบเอกสาร\\nกรุงเทพมหานคร 123\"}]<|endofassistant|>",
          "elements": [
            {
              "index": 0,
              "category": "Text",
              "text": "ภาษาไทย ทดสอบเอกสาร\nกรุงเทพมหานคร 123",
              "confidence": null,
              "native_bbox": [
                29.0,
                39.0,
                322.0,
                112.0
              ],
              "bbox": [
                28.571428571428573,
                38.30357142857142,
                317.2413793103448,
                110.0
              ],
              "geometry_status": "valid"
            }
          ],
          "tables": [],
          "image": {
            "width": 800,
            "height": 220
          },
          "model_image": {
            "width": 812,
            "height": 224
          },
          "coordinate_frame": "input_image_pixels",
          "reading_order": "model_sequence",
          "confidence": null
        },
        "error": null,
        "duration_ms": 2922.0
      }
    ],
    "count": 2,
    "succeeded": 2,
    "failed": 0,
    "execution": "sequential_wrapper"
  },
  "meta": {
    "api_version": "v1",
    "request_id": "cbdef36709a04a63ab9f806296ffa54d",
    "model": "dots-studio/dots.ocr",
    "revision": "c0111ce6bc07803dbc267932ffef0ae3a51dc951",
    "backend": "transformers",
    "device": "cuda",
    "dtype": "bfloat16",
    "duration_ms": 5328.0
  }
}
```

## Table

[Complete actual response](../benchmarks/ocr-final/response-table.json)

```json
{
  "data": {
    "schema_version": "1.0",
    "text": "<table><thead><tr><td>Item</td><td>Quantity</td><td>Price</td></tr></thead><tbody><tr><td>Notebook</td><td>2</td><td>100</td></tr><tr><td>Pen</td><td>3</td><td>50</td></tr><tr><td>Total</td><td>5</td><td>150</td></tr></tbody></table>",
    "native_output": "[{\"bbox\": [28, 27, 762, 390], \"category\": \"Table\", \"text\": \"<table><thead><tr><td>Item</td><td>Quantity</td><td>Price</td></tr></thead><tbody><tr><td>Notebook</td><td>2</td><td>100</td></tr><tr><td>Pen</td><td>3</td><td>50</td></tr><tr><td>Total</td><td>5</td><td>150</td></tr></tbody></table>\"}]<|endofassistant|>",
    "elements": [
      {
        "index": 0,
        "category": "Table",
        "text": "<table><thead><tr><td>Item</td><td>Quantity</td><td>Price</td></tr></thead><tbody><tr><td>Notebook</td><td>2</td><td>100</td></tr><tr><td>Pen</td><td>3</td><td>50</td></tr><tr><td>Total</td><td>5</td><td>150</td></tr></tbody></table>",
        "confidence": null,
        "native_bbox": [
          28.0,
          27.0,
          762.0,
          390.0
        ],
        "bbox": [
          27.586206896551726,
          27.120535714285715,
          750.7389162561576,
          391.74107142857144
        ],
        "geometry_status": "valid"
      }
    ],
    "tables": [
      0
    ],
    "image": {
      "width": 800,
      "height": 450
    },
    "model_image": {
      "width": 812,
      "height": 448
    },
    "coordinate_frame": "input_image_pixels",
    "reading_order": "model_sequence",
    "confidence": null
  },
  "meta": {
    "api_version": "v1",
    "request_id": "69daf4e2bf294e70bfb414d707b3a224",
    "model": "dots-studio/dots.ocr",
    "revision": "c0111ce6bc07803dbc267932ffef0ae3a51dc951",
    "backend": "transformers",
    "device": "cuda",
    "dtype": "bfloat16",
    "duration_ms": 4062.0
  }
}
```

## Full page

[Complete actual response](../benchmarks/ocr-final/response-full_page.json)

```json
{
  "data": {
    "schema_version": "1.0",
    "text": "SYNTHETIC REPORT 2026\nSection 1: Document processing and evaluation.\nSection 2: Document processing and evaluation.\nSection 3: Document processing and evaluation.\nSection 4: Document processing and evaluation.\nSection 5: Document processing and evaluation.\nSection 6: Document processing and evaluation.\nSection 7: Document processing and evaluation.\nSection 8: Document processing and evaluation.\nSection 9: Document processing and evaluation.\nSection 10: Document processing and evaluation.",
    "native_output": "[{\"bbox\": [39, 44, 307, 69], \"category\": \"Section-header\", \"text\": \"SYNTHETIC REPORT 2026\"}, {\"bbox\": [39, 109, 421, 132], \"category\": \"Text\", \"text\": \"Section 1: Document processing and evaluation.\"}, {\"bbox\": [39, 185, 421, 208], \"category\": \"Text\", \"text\": \"Section 2: Document processing and evaluation.\"}, {\"bbox\": [39, 261, 421, 284], \"category\": \"Text\", \"text\": \"Section 3: Document processing and evaluation.\"}, {\"bbox\": [39, 336, 421, 359], \"category\": \"Text\", \"text\": \"Section 4: Document processing and evaluation.\"}, {\"bbox\": [39, 412, 421, 435], \"category\": \"Text\", \"text\": \"Section 5: Document processing and evaluation.\"}, {\"bbox\": [39, 488, 421, 511], \"category\": \"Text\", \"text\": \"Section 6: Document processing and evaluation.\"}, {\"bbox\": [39, 563, 421, 586], \"category\": \"Text\", \"text\": \"Section 7: Document processing and evaluation.\"}, {\"bbox\": [39, 639, 421, 662], \"category\": \"Text\", \"text\": \"Section 8: Document processing and evaluation.\"}, {\"bbox\": [39, 715, 421, 738], \"category\": \"Text\", \"text\": \"Section 9: Document processing and evaluation.\"}, {\"bbox\": [39, 791, 429, 814], \"category\": \"Text\", \"text\": \"Section 10: Document processing and evaluation.\"}]<|endofassistant|>",
    "elements": [
      {
        "index": 0,
        "category": "Section-header",
        "text": "SYNTHETIC REPORT 2026",
        "confidence": null,
        "native_bbox": [
          39.0,
          44.0,
          307.0,
          69.0
        ],
        "bbox": [
          46.42857142857143,
          52.38095238095238,
          365.4761904761905,
          82.14285714285714
        ],
        "geometry_status": "valid"
      },
      {
        "index": 1,
        "category": "Text",
        "text": "Section 1: Document processing and evaluation.",
        "confidence": null,
        "native_bbox": [
          39.0,
          109.0,
          421.0,
          132.0
        ],
        "bbox": [
          46.42857142857143,
          129.76190476190476,
          501.1904761904762,
          157.14285714285714
        ],
        "geometry_status": "valid"
      },
      {
        "index": 2,
        "category": "Text",
        "text": "Section 2: Document processing and evaluation.",
        "confidence": null,
        "native_bbox": [
          39.0,
          185.0,
          421.0,
          208.0
        ],
        "bbox": [
          46.42857142857143,
          220.23809523809524,
          501.1904761904762,
          247.61904761904762
        ],
        "geometry_status": "valid"
      },
      {
        "index": 3,
        "category": "Text",
        "text": "Section 3: Document processing and evaluation.",
        "confidence": null,
        "native_bbox": [
          39.0,
          261.0,
          421.0,
          284.0
        ],
        "bbox": [
          46.42857142857143,
          310.7142857142857,
          501.1904761904762,
          338.0952380952381
        ],
        "geometry_status": "valid"
      },
      {
        "index": 4,
        "category": "Text",
        "text": "Section 4: Document processing and evaluation.",
        "confidence": null,
        "native_bbox": [
          39.0,
          336.0,
          421.0,
          359.0
        ],
        "bbox": [
          46.42857142857143,
          400.0,
          501.1904761904762,
          427.38095238095235
        ],
        "geometry_status": "valid"
      },
      {
        "index": 5,
        "category": "Text",
        "text": "Section 5: Document processing and evaluation.",
        "confidence": null,
        "native_bbox": [
          39.0,
          412.0,
          421.0,
          435.0
        ],
        "bbox": [
          46.42857142857143,
          490.4761904761905,
          501.1904761904762,
          517.8571428571429
        ],
        "geometry_status": "valid"
      },
      {
        "index": 6,
        "category": "Text",
        "text": "Section 6: Document processing and evaluation.",
        "confidence": null,
        "native_bbox": [
          39.0,
          488.0,
          421.0,
          511.0
        ],
        "bbox": [
          46.42857142857143,
          580.952380952381,
          501.1904761904762,
          608.3333333333334
        ],
        "geometry_status": "valid"
      },
      {
        "index": 7,
        "category": "Text",
        "text": "Section 7: Document processing and evaluation.",
        "confidence": null,
        "native_bbox": [
          39.0,
          563.0,
          421.0,
          586.0
        ],
        "bbox": [
          46.42857142857143,
          670.2380952380952,
          501.1904761904762,
          697.6190476190476
        ],
        "geometry_status": "valid"
      },
      {
        "index": 8,
        "category": "Text",
        "text": "Section 8: Document processing and evaluation.",
        "confidence": null,
        "native_bbox": [
          39.0,
          639.0,
          421.0,
          662.0
        ],
        "bbox": [
          46.42857142857143,
          760.7142857142857,
          501.1904761904762,
          788.0952380952381
        ],
        "geometry_status": "valid"
      },
      {
        "index": 9,
        "category": "Text",
        "text": "Section 9: Document processing and evaluation.",
        "confidence": null,
        "native_bbox": [
          39.0,
          715.0,
          421.0,
          738.0
        ],
        "bbox": [
          46.42857142857143,
          851.1904761904761,
          501.1904761904762,
          878.5714285714286
        ],
        "geometry_status": "valid"
      },
      {
        "index": 10,
        "category": "Text",
        "text": "Section 10: Document processing and evaluation.",
        "confidence": null,
        "native_bbox": [
          39.0,
          791.0,
          429.0,
          814.0
        ],
        "bbox": [
          46.42857142857143,
          941.6666666666666,
          510.7142857142857,
          969.047619047619
        ],
        "geometry_status": "valid"
      }
    ],
    "tables": [],
    "image": {
      "width": 1000,
      "height": 1400
    },
    "model_image": {
      "width": 840,
      "height": 1176
    },
    "coordinate_frame": "input_image_pixels",
    "reading_order": "model_sequence",
    "confidence": null
  },
  "meta": {
    "api_version": "v1",
    "request_id": "7a1938acb28a4c8ab23889adeb8ed50a",
    "model": "dots-studio/dots.ocr",
    "revision": "c0111ce6bc07803dbc267932ffef0ae3a51dc951",
    "backend": "transformers",
    "device": "cuda",
    "dtype": "bfloat16",
    "duration_ms": 14594.0
  }
}
```

## Cropped region

[Complete actual response](../benchmarks/ocr-final/response-crop.json)

```json
{
  "data": {
    "schema_version": "1.0",
    "text": "Document 123",
    "native_output": "[{\"bbox\": [7, 15, 183, 37], \"category\": \"Text\", \"text\": \"Document 123\"}]<|endofassistant|>",
    "elements": [
      {
        "index": 0,
        "category": "Text",
        "text": "Document 123",
        "confidence": null,
        "native_bbox": [
          7.0,
          15.0,
          183.0,
          37.0
        ],
        "bbox": [
          7.0588235294117645,
          18.75,
          184.53781512605042,
          46.25
        ],
        "geometry_status": "valid"
      }
    ],
    "tables": [],
    "image": {
      "width": 480,
      "height": 70
    },
    "model_image": {
      "width": 476,
      "height": 56
    },
    "coordinate_frame": "input_image_pixels",
    "reading_order": "model_sequence",
    "confidence": null
  },
  "meta": {
    "api_version": "v1",
    "request_id": "ec880d04a9ee4f5b8a786f7653bce9dd",
    "model": "dots-studio/dots.ocr",
    "revision": "c0111ce6bc07803dbc267932ffef0ae3a51dc951",
    "backend": "transformers",
    "device": "cuda",
    "dtype": "bfloat16",
    "duration_ms": 1047.0
  }
}
```

## Corrupt input/error

[Complete actual response](../benchmarks/ocr-final/response-corrupt.json)

```json
{
  "error": {
    "code": "INVALID_IMAGE",
    "message": "The uploaded image cannot be decoded."
  },
  "meta": {
    "request_id": "b8b2c949598d4ba7b71ceb657062f011",
    "api_version": "v1"
  }
}
```

MOCR responses are under `benchmarks/mocr-vllm-final/`. Batch result objects are exactly the Single data schema; do not map the outer results list as elements. Native rectangles are not OpenThai four-point polygons. See API_CONTRACT.md.
