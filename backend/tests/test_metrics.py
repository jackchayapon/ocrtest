import pytest

from app.services.metrics_service import calculate_metrics, levenshtein, normalize_text


@pytest.mark.parametrize(
    "reference,prediction,distance",
    [("kitten", "sitting", 3), ("", "x", 1), ("ไทย", "ไทย", 0), ("a", "", 1)],
)
def test_unicode_levenshtein(reference, prediction, distance):
    assert levenshtein(reference, prediction) == distance


def test_conservative_normalization():
    assert normalize_text("  cafe\u0301\r\n  ไทย!\t  ") == "café ไทย!"
    assert normalize_text("จากัด") != normalize_text("จำกัด")


def test_cer_wer_and_exact():
    result = calculate_metrics("cat dog", "cat dogs")
    assert result["cer"] == 1 / 8
    assert result["wer"] == 1 / 2
    assert result["exact_match"] is False
    assert calculate_metrics("ไทย\n ภาษา", " ไทย   ภาษา ") == {
        "cer": 0.0,
        "wer": 0.0,
        "exact_match": True,
    }


def test_empty_reference_and_rates_over_one():
    assert calculate_metrics("", "") == {"cer": 0.0, "wer": 0.0, "exact_match": True}
    assert calculate_metrics("x", "") == {"cer": None, "wer": None, "exact_match": False}
    assert calculate_metrics("abcdefgh", "a")["cer"] == 7


def test_tokenizer_can_be_replaced():
    assert calculate_metrics("ภาษาไทย", "ภาษาไท", tokenizer=list)["wer"] == 1 / 6


def test_long_near_exact_document():
    text = "ภาษาไทย " * 10000
    assert levenshtein(text, text[:30000] + "X" + text[30001:]) == 1
