import json
import math
from typing import Literal

from pydantic import BaseModel, Field, FiniteFloat

from app.errors import ServiceError


class Dimensions(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class Element(BaseModel):
    index: int
    category: str
    text: str | None
    confidence: None = None
    native_bbox: list[FiniteFloat] | None = Field(
        default=None, min_length=4, max_length=4
    )
    bbox: list[FiniteFloat] | None = Field(default=None, min_length=4, max_length=4)
    geometry_status: Literal["valid", "absent", "out_of_bounds"] = "absent"


class OCRData(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    text: str
    native_output: str
    elements: list[Element]
    tables: list[int]
    image: Dimensions
    model_image: Dimensions
    coordinate_frame: Literal["input_image_pixels"] = "input_image_pixels"
    reading_order: Literal["model_sequence"] = "model_sequence"
    confidence: None = None


def invalid_output():
    return ServiceError(
        "MODEL_OUTPUT_INVALID", "The model did not return valid layout JSON.", 502
    )


def reject_constant(value):
    raise ValueError(value)


def parse_output(raw, image_size, model_size):
    """Keep exact native text and order; scale model-image rectangles once."""
    if not isinstance(raw, str) or len(raw) > 262144:
        raise invalid_output()
    content = raw.strip()
    # Observed from the pinned checkpoint: this native assistant terminator is
    # not classified as a tokenizer special token. Retain it in native_output.
    if content.endswith("<|endofassistant|>"):
        content = content.removesuffix("<|endofassistant|>").rstrip()
    if content.startswith("```json\n") and content.endswith("\n```"):
        content = content[8:-4]
    try:
        layouts = json.loads(content, parse_constant=reject_constant)
    except (ValueError, RecursionError):
        raise invalid_output() from None
    if not isinstance(layouts, list) or len(layouts) > 1024:
        raise invalid_output()
    width, height = image_size
    model_width, model_height = model_size
    if min(width, height, model_width, model_height) <= 0:
        raise invalid_output()
    elements = []
    for index, item in enumerate(layouts):
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("category"), str)
            or not item["category"]
        ):
            raise invalid_output()
        text = item.get("text")
        if text is not None and not isinstance(text, str):
            raise invalid_output()
        native = item.get("bbox")
        mapped = None
        geometry_status = "absent"
        if native is not None:
            if (
                not isinstance(native, list)
                or len(native) != 4
                or any(
                    isinstance(v, bool)
                    or not isinstance(v, (int, float))
                    or not math.isfinite(v)
                    for v in native
                )
                or native[2] <= native[0]
                or native[3] <= native[1]
            ):
                raise invalid_output()
            mapped = [
                v * (width / model_width if i % 2 == 0 else height / model_height)
                for i, v in enumerate(native)
            ]
            if not all(math.isfinite(value) for value in mapped):
                raise invalid_output()
            geometry_status = "valid"
            if (
                native[0] < 0
                or native[1] < 0
                or native[2] > model_width
                or native[3] > model_height
            ):
                # Observed on the real blank fixture. Never clip/fabricate a
                # plausible box from an out-of-frame model prediction.
                geometry_status = "out_of_bounds"
                mapped = None
        elements.append(
            Element(
                index=index,
                category=item["category"],
                text=text,
                native_bbox=native,
                bbox=mapped,
                geometry_status=geometry_status,
            )
        )
    return OCRData(
        text="\n".join(e.text for e in elements if e.text is not None),
        native_output=raw,
        elements=elements,
        tables=[e.index for e in elements if e.category == "Table"],
        image=Dimensions(width=width, height=height),
        model_image=Dimensions(width=model_width, height=model_height),
    )
