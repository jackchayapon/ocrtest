"""Thai descriptions of canonical character events (not word errors)."""

from collections import Counter

from app.services.character_statistics import character_identity

STATE_LABELS = {
    "ready": "ประเมินสำเร็จ",
    "outdated": "ผลประเมินล้าสมัย",
    "no_confirmed_gt": "ยังไม่ยืนยันข้อความจริง",
    "pipeline_failed": "Field ประมวลผลล้มเหลว",
    "no_prediction": "ไม่มีผล OCR ของ Field",
    "alignment_unavailable": "รายละเอียดไม่ตรงกับผลประเมินเดิม",
}


def character_description(value):
    if value is None:
        return "ไม่มีอักขระ"
    identity = character_identity(value)
    return f'"{identity["display"]}" ({identity["name"]})'


def explain_event(kind, expected, predicted, count=1):
    if kind == "substitution":
        return f"อ่านผิด {character_description(expected)} เป็น {character_description(predicted)} {count} ครั้ง"
    if kind == "insertion":
        return f"อ่านเกิน {character_description(predicted)} {count} ครั้ง"
    return f"อ่านขาดหาย {character_description(expected)} {count} ครั้ง"


def explain_events(events):
    counts = Counter((e["error_type"], e["ground_truth_unit"], e["ocr_unit"]) for e in events)
    return [explain_event(*key, count) for key, count in counts.items()] or [
        "ไม่พบข้อผิดพลาดในการอ่านตัวอักษร"
    ]
