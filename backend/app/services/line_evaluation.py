from itertools import zip_longest

from app.services.field_service import compact_comparison, compare_field


def line_evaluations(prediction, reference, *, detail=False):
    """Pair original lines by position without dropping blanks or extra lines."""
    def lines(text):
        return (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")

    compare = compare_field if detail else compact_comparison
    return [{key: value for key, value in compare(predicted, expected).items() if key != "events"}
            for predicted, expected in zip_longest(lines(prediction), lines(reference), fillvalue="")]
