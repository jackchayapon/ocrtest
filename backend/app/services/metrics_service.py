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
    previous = list(range(len(prediction) + 1))
    for i, left in enumerate(reference, 1):
        current = [i]
        for j, right in enumerate(prediction, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


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
