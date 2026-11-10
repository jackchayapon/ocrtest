from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete, select

from app.core.config import Settings
from app.db.models import Category, DocumentType, OCRModel, PipelineConfig
from app.services.document_type_service import DEFAULT_TYPES, normalized_name

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
    # Stable IDs prevent re-creating edited catalog entries at the next startup.
    for source, kind, version, weight in [
        *[("official", kind, version, "default") for kind in ("det", "rec")
          for version in ("5", "6")],
        *[("official", kind, version, weight) for kind in ("det", "rec")
          for version in ("5", "6") for weight in ("baseline", "thai_ft_v1", "thai_ft_v2")],
        *[("custom", kind, version, weight) for kind in ("det", "rec")
          for version in ("5", "6") for weight in ("baseline", "thai_ft_v1", "thai_ft_v2")],
    ]:
        model_id = str(uuid5(NAMESPACE_URL, f"ocrtest/model/{source}/{kind}/{version}/{weight}"))
        if session.get(OCRModel, model_id) is None:
            stem = "text-detection" if kind == "det" else "text-recognition"
            query = f"version={version}" + (f"&model={weight}" if weight != "default" else "")
            session.add(OCRModel(id=model_id, name=f"{kind.upper()} V{version} · {weight}",
                source=source, kind=kind, version=version, weight=weight,
                single_path=f"/api/v1/{stem}s?{query}", batch_path=f"/api/v1/{stem}-batches?{query}"))
    names = set(session.scalars(select(DocumentType.normalized_name)))
    session.add_all(DocumentType(name=name, normalized_name=normalized_name(name), system=True)
                    for name in DEFAULT_TYPES if normalized_name(name) not in names)
    existing = set(session.scalars(select(Category.code)))
    session.add_all(
        Category(code=code, display_name=name)
        for code, name in CATEGORIES.items()
        if code not in existing
    )
    # Retire built-in configurations only; PipelineRun stores independent snapshots.
    session.execute(delete(PipelineConfig).where(PipelineConfig.execution_mode.is_(None)))
    session.commit()
