import re
import unicodedata
from collections.abc import Sequence


def normalize_text(text: str) -> str:
    """NFC, normalized newlines, trim and collapse whitespace; preserve spelling/punctuation."""
    return re.sub(
        r"\s+", " ", unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    ).strip()


def levenshtein(reference: Sequence, prediction: Sequence) -> int:
    if reference == prediction:
        return 0
    # Remove common context before the quadratic DP; long near-exact OCR remains fast.
    prefix = 0
    while prefix < min(len(reference), len(prediction)) and reference[prefix] == prediction[prefix]:
        prefix += 1
    reference, prediction = reference[prefix:], prediction[prefix:]
    suffix = 0
    while (
        suffix < min(len(reference), len(prediction))
        and reference[-suffix - 1] == prediction[-suffix - 1]
    ):
        suffix += 1
    if suffix:
        reference, prediction = reference[:-suffix], prediction[:-suffix]
    if not reference or not prediction:
        return max(len(reference), len(prediction))
    if len(reference) < len(prediction):
        reference, prediction = prediction, reference
    return _distance_row(reference, prediction)[-1]


def _distance_row(reference: Sequence, prediction: Sequence) -> list[int]:
    """Shared unit-cost recurrence for both metrics and alignment."""
    previous = list(range(len(prediction) + 1))
    for i, left in enumerate(reference, 1):
        current = [i]
        for j, right in enumerate(prediction, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left != right)))
        previous = current
    return previous


def align_errors(
    reference: Sequence, prediction: Sequence, ref_offset=0, pred_offset=0
) -> list[dict]:
    """Optimal Hirschberg alignment, linear DP space. Positions are zero-based
    normalized code-point/token offsets; missing units have null positions.
    Ties use the leftmost split, then diagonal, deletion, insertion.
    """
    prefix = 0
    while prefix < min(len(reference), len(prediction)) and reference[prefix] == prediction[prefix]:
        prefix += 1
    reference, prediction = reference[prefix:], prediction[prefix:]
    ref_offset, pred_offset = ref_offset + prefix, pred_offset + prefix
    suffix = 0
    while (
        suffix < min(len(reference), len(prediction))
        and reference[-suffix - 1] == prediction[-suffix - 1]
    ):
        suffix += 1
    if suffix:
        reference, prediction = reference[:-suffix], prediction[:-suffix]

    def event(kind, i, j):
        return dict(
            error_type=kind,
            ground_truth_unit=reference[i] if i is not None else None,
            ocr_unit=prediction[j] if j is not None else None,
            ground_truth_position=ref_offset + i if i is not None else None,
            ocr_position=pred_offset + j if j is not None else None,
        )

    if not reference:
        return [event("insertion", None, j) for j in range(len(prediction))]
    if not prediction:
        return [event("deletion", i, None) for i in range(len(reference))]
    if min(len(reference), len(prediction)) == 1:
        rows = [list(range(len(prediction) + 1))]
        for i, left in enumerate(reference, 1):
            row = [i]
            for j, right in enumerate(prediction, 1):
                row.append(min(row[-1] + 1, rows[-1][j] + 1, rows[-1][j - 1] + (left != right)))
            rows.append(row)
        result, i, j = [], len(reference), len(prediction)
        while i or j:
            if (
                i
                and j
                and rows[i][j] == rows[i - 1][j - 1] + (reference[i - 1] != prediction[j - 1])
            ):
                if reference[i - 1] != prediction[j - 1]:
                    result.append(event("substitution", i - 1, j - 1))
                i, j = i - 1, j - 1
            elif i and rows[i][j] == rows[i - 1][j] + 1:
                result.append(event("deletion", i - 1, None))
                i -= 1
            else:
                result.append(event("insertion", None, j - 1))
                j -= 1
        return result[::-1]
    middle = len(reference) // 2
    left = _distance_row(reference[:middle], prediction)
    right = _distance_row(reference[middle:][::-1], prediction[::-1])
    split = min((left[j] + right[len(prediction) - j], j) for j in range(len(prediction) + 1))[1]
    del left, right
    return align_errors(
        reference[:middle], prediction[:split], ref_offset, pred_offset
    ) + align_errors(
        reference[middle:], prediction[split:], ref_offset + middle, pred_offset + split
    )


def error_breakdown(prediction: str, ground_truth: str) -> list[dict]:
    reference, predicted = normalize_text(ground_truth), normalize_text(prediction)
    return [
        dict(error_level=level, **event)
        for level, ref, pred in (
            ("char", reference, predicted),
            ("word", whitespace_tokenizer(reference), whitespace_tokenizer(predicted)),
        )
        for event in align_errors(ref, pred)
    ]


def whitespace_tokenizer(text: str) -> list[str]:
    """MVP tokenization: Thai words without spaces stay in one token. Prefer CER for Thai."""
    return text.split()


def calculate_metrics(prediction: str, ground_truth: str, tokenizer=whitespace_tokenizer) -> dict:
    prediction = normalize_text(prediction)
    reference = normalize_text(ground_truth)
    reference_words, predicted_words = tokenizer(reference), tokenizer(prediction)
    return {
        # Empty reference has undefined rates if prediction is nonempty; never emit NaN/Infinity.
        "cer": levenshtein(reference, prediction) / len(reference)
        if reference
        else (0.0 if not prediction else None),
        "wer": levenshtein(reference_words, predicted_words) / len(reference_words)
        if reference_words
        else (0.0 if not predicted_words else None),
        "exact_match": prediction == reference,
    }
