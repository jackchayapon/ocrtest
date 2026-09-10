from sqlalchemy import select

from app.core.config import Settings
from app.db.models import Category, PipelineConfig

CATEGORIES = {
    "thai_text": "Thai text",
    "thai_digit": "Thai digits",
    "arabic_digit": "Arabic digits",
    "english_text": "English text",
    "mixed_language": "Mixed language",
    "sentence": "Sentence",
    "handwriting": "Handwriting",
    "strikethrough": "Strikethrough",
    "stamp": "Stamp",
    "table_text": "Table text",
    "low_quality": "Low quality",
    "blur": "Blur",
    "skew": "Skew",
    "small_text": "Small text",
}


def seed_database(session, settings: Settings):
    existing = set(session.scalars(select(Category.code)))
    session.add_all(
        Category(code=code, display_name=name)
        for code, name in CATEGORIES.items()
        if code not in existing
    )
    configs = [
        dict(
            pipeline_id="mint",
            name="Mint Custom",
            base_url=settings.mint_gateway_base_url or settings.model_gateway_base_url,
            endpoint=settings.mint_ocr_endpoint,
            engine="custom",
            query_params={"engine": "custom"},
        ),
        dict(
            pipeline_id="hutch_crop",
            name="Hutch Crop",
            base_url=settings.hutch_gateway_base_url or settings.model_gateway_base_url,
            endpoint=settings.hutch_crop_endpoint,
            engine="paddle",
            query_params={"engine": "paddle"},
        ),
        dict(
            pipeline_id="hutch_full",
            name="Hutch Full",
            base_url=settings.hutch_full_base_url or settings.model_gateway_base_url,
            endpoint=settings.hutch_full_endpoint or "/api/v1/ocr-results",
            engine="paddle",
            query_params={"engine": "paddle"},
        ),
    ]
    existing_pipelines = set(session.scalars(select(PipelineConfig.pipeline_id)))
    session.add_all(
        PipelineConfig(**item) for item in configs if item["pipeline_id"] not in existing_pipelines
    )
    session.commit()
