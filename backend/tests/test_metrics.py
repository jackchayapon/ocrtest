import pytest

from app.services.metrics_service import (
    calculate_cer,
    calculate_metrics,
    calculate_wer,
    is_exact_match,
    levenshtein,
    normalize_text,
    tokenize_words,
)


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
    assert calculate_metrics("x", "") == {"cer": 1.0, "wer": 1.0, "exact_match": False}
    assert calculate_metrics("abcdefgh", "a")["cer"] == 7


def test_tokenizer_can_be_replaced():
    assert calculate_metrics("ภาษาไทย", "ภาษาไท", tokenizer=list)["wer"] == 1 / 6


def test_long_near_exact_document():
    text = "ภาษาไทย " * 10000
    assert levenshtein(text, text[:30000] + "X" + text[30001:]) == 1


def test_requested_whitespace_and_empty_reference_policy():
    assert calculate_cer(" A\n B\tC ", "ABC", return_counts=True) == (2 / 5, 2, 5)
    assert calculate_cer("A B", "AB", ignore_whitespace=True) == 0.0
    assert calculate_cer("A B", "AB", ignore_whitespace=False) == 1 / 3
    assert not is_exact_match("A B", "AB")
    assert is_exact_match("  cafe\u0301  ", "café")
    for scorer in (calculate_cer, calculate_wer):
        assert scorer(" \n", "", return_counts=True) == (0.0, 0, 0)
        assert scorer("", "abc", return_counts=True)[0] == 1.0


def test_thai_words_without_spaces_use_newmm():
    assert tokenize_words("ฉันกินข้าว") == ["ฉัน", "กินข้าว"]
    assert tokenize_words("ฉันกินข้าว", thai=False) == ["ฉันกินข้าว"]
    assert calculate_wer("ฉันกินข้าว", "ฉัน", return_counts=True) == (1 / 2, 1, 2)
    assert calculate_metrics("ฉัน", "ฉันกินข้าว")["wer"] == 1 / 2


@pytest.mark.parametrize("gt,ocr", [("ก่า", "กา"), ("กี่", "กิ่"), ("คำ!", "คำ?")])
def test_marks_and_punctuation_are_included_in_character_errors(gt, ocr):
    from app.services.field_service import compare_field

    result = compare_field(ocr, gt)
    assert result["character_edits"] == 1
    assert result["cer"] > 0
    assert len([span for span in result["spans"] if span["kind"] != "equal"]) == 1


@pytest.mark.parametrize("gt,ocr", [
    ("ฉันกินข้าว\nแมว", "ฉันกินปลา แมว"),
    ("A  B\nC", "ABX"), ("", "extra"), ("ABC", ""),
])
def test_compact_counts_and_highlights_share_metric_units(gt, ocr):
    from app.services.field_service import compact_comparison, compare_field

    compact, detailed = compact_comparison(ocr, gt), compare_field(ocr, gt)
    assert all(detailed[key] == value for key, value in compact.items())
    assert (compact["cer"], compact["character_edits"], compact["gt_characters"]) == calculate_cer(gt, ocr, return_counts=True)
    assert (compact["wer"], compact["word_edits"], compact["gt_words"]) == calculate_wer(gt, ocr, return_counts=True)
