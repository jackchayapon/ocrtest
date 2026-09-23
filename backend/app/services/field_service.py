from app.db.models import OCRField, now
from app.repositories.field_repository import FieldRepository
from app.services.metrics_service import (
    calculate_metrics,
    error_breakdown,
    normalize_text,
    whitespace_tokenizer,
)


def compare_field(prediction, ground_truth):
    predicted, reference = normalize_text(prediction), normalize_text(ground_truth)
    events = error_breakdown(prediction, ground_truth)
    # Reconstruct matches/gaps from the existing ordered alignment, not another diff algorithm.
    spans, ref_cursor, pred_cursor = [], 0, 0
    for event in (e for e in events if e["error_level"] == "char"):
        kind = event["error_type"]
        position = event["ocr_position"]
        if position is None:
            position = pred_cursor + event["ground_truth_position"] - ref_cursor
        gap = position - pred_cursor
        if gap:
            spans.append(dict(kind="equal", text=predicted[pred_cursor:position]))
        pred_cursor, ref_cursor = position, ref_cursor + gap
        spans.append(
            dict(kind=kind, text=event["ocr_unit"] or "", missing=event["ground_truth_unit"])
        )
        if kind != "deletion":
            pred_cursor += 1
        if kind != "insertion":
            ref_cursor += 1
    if pred_cursor < len(predicted):
        spans.append(dict(kind="equal", text=predicted[pred_cursor:]))
    return dict(
        **calculate_metrics(prediction, ground_truth),
        character_edits=sum(e["error_level"] == "char" for e in events),
        word_edits=sum(e["error_level"] == "word" for e in events),
        gt_characters=len(reference),
        gt_words=len(whitespace_tokenizer(reference)),
        normalized_ocr=predicted,
        normalized_ground_truth=reference,
        events=events,
        spans=spans,
    )


def field_summary(fields):
    confirmed = [f.evaluation for f in fields if f.confirmed_at and f.evaluation]
    if not confirmed:
        return dict(
            confirmed_fields=0, total_fields=len(fields), cer=None, wer=None, exact_match=None
        )
    chars = sum(f["gt_characters"] for f in confirmed)
    words = sum(f["gt_words"] for f in confirmed)
    char_edits = sum(f["character_edits"] for f in confirmed)
    word_edits = sum(f["word_edits"] for f in confirmed)
    return dict(
        confirmed_fields=len(confirmed),
        total_fields=len(fields),
        character_edits=char_edits,
        word_edits=word_edits,
        gt_characters=chars,
        gt_words=words,
        cer=char_edits / chars if chars else (None if char_edits else 0.0),
        wer=word_edits / words if words else (None if word_edits else 0.0),
        exact_match=all(f["exact_match"] for f in confirmed),
    )


class FieldService:
    def __init__(self, session):
        self.repository = FieldRepository(session)

    @staticmethod
    def generate(run):
        if run.status != "success" or run.fields:
            return
        # No text splitting or cross-pipeline matching. Null geometry remains null.
        for index, box in enumerate(run.boxes or []):
            if not isinstance(box.get("text"), str):
                continue
            run.fields.append(
                OCRField(
                    field_index=index,
                    ocr_text=box["text"],
                    confidence=box.get("rec_confidence"),
                    geometry={
                        key: box.get(key)
                        for key in ("polygon", "bbox", "crop_polygon", "crop_bbox")
                    },
                )
            )

    def list_fields(self, case_id, run_id):
        run = self.repository.run(case_id, run_id)
        return run.fields

    def check(self, case_id, run_id, field_id, text):
        field = self.repository.field(case_id, run_id, field_id)
        return compare_field(field.ocr_text, text)

    def update(self, case_id, run_id, field_id, data):
        field = self.repository.field(case_id, run_id, field_id, lock=True)
        field.ground_truth_raw = data.ground_truth_raw
        field.ground_truth_normalized = normalize_text(data.ground_truth_raw)
        field.confirmed_at = now() if data.confirmed else None
        # Replacement JSON snapshot: repeated checks/confirmations cannot append duplicate events.
        field.evaluation = (
            compare_field(field.ocr_text, data.ground_truth_raw) if data.confirmed else None
        )
        field.updated_at = now()
        self.repository.save()
        return field
