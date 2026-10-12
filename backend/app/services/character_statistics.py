"""On-demand code-point statistics from canonical alignment; never persisted."""

import unicodedata
from collections import Counter

from app.core.errors import AppError
from app.services.metrics_service import align_errors, character_text

RULES_VERSION = "nfc-whitespace-codepoint-v1/wer-newmm-v1"
THAI_NAMES = dict(
    zip(
        "กขฃคฅฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรลวศษสหฬอฮ",
        "ก ไก่,ข ไข่,ฃ ขวด,ค ควาย,ฅ คน,ฆ ระฆัง,ง งู,จ จาน,ฉ ฉิ่ง,ช ช้าง,ซ โซ่,ฌ เฌอ,ญ หญิง,ฎ ชฎา,ฏ ปฏัก,ฐ ฐาน,ฑ มณโฑ,ฒ ผู้เฒ่า,ณ เณร,ด เด็ก,ต เต่า,ถ ถุง,ท ทหาร,ธ ธง,น หนู,บ ใบไม้,ป ปลา,ผ ผึ้ง,ฝ ฝา,พ พาน,ฟ ฟัน,ภ สำเภา,ม ม้า,ย ยักษ์,ร เรือ,ล ลิง,ว แหวน,ศ ศาลา,ษ ฤๅษี,ส เสือ,ห หีบ,ฬ จุฬา,อ อ่าง,ฮ นกฮูก".split(
            ","
        ),
    )
)
THAI_NAMES.update(
    dict(
        zip(
            "่้๊๋็์ัำิีึืุูะาเแโใไ",
            "ไม้เอก,ไม้โท,ไม้ตรี,ไม้จัตวา,ไม้ไต่คู้,การันต์,ไม้หันอากาศ,สระอำ,สระอิ,สระอี,สระอึ,สระอือ,สระอุ,สระอู,สระอะ,สระอา,สระเอ,สระแอ,สระโอ,สระใอ,สระไอ".split(
                ","
            ),
        )
    )
)
THAI_NAMES.update({c: f"เลขไทย {i}" for i, c in enumerate("๐๑๒๓๔๕๖๗๘๙")})

THAI_NAMES.update({char: f"อักษรอังกฤษ {char}" for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"})
THAI_NAMES.update({char: f"เลขอารบิก {char}" for char in "0123456789"})
THAI_NAMES.update({" ": "ช่องว่าง", ".": "จุด", ",": "จุลภาค", "-": "ขีดกลาง", "!": "อัศเจรีย์", "?": "ปรัศนี"})


def character_identity(char):
    return dict(
        character=char,
        code_point=f"U+{ord(char):04X}",
        name=THAI_NAMES.get(char, unicodedata.name(char, "Unnamed Unicode character")),
        display=(
            "◌" + char
            if unicodedata.category(char).startswith("M")
            else "␣"
            if char == " "
            else char
        ),
    )


def character_statistics(prediction, ground_truth):
    reference, predicted = character_text(ground_truth), character_text(prediction)
    if len(reference) + len(predicted) > 40_000:
        raise AppError(
            "Evaluation detail exceeds 40,000 normalized characters; select a field", 413
        )
    left, right = reference, predicted
    prefix = 0
    while prefix < min(len(left), len(right)) and left[prefix] == right[prefix]:
        prefix += 1
    left, right = left[prefix:], right[prefix:]
    suffix = 0
    while suffix < min(len(left), len(right)) and left[-suffix - 1] == right[-suffix - 1]:
        suffix += 1
    if suffix:
        left, right = left[:-suffix], right[:-suffix]
    if len(left) * len(right) > 16_000_000:
        raise AppError("Alignment work limit exceeded; select a smaller field", 413)
    events = align_errors(reference, predicted)
    counts = Counter(e["error_type"] for e in events)
    by_char, pairs = {}, Counter()
    for event in events:
        kind = event["error_type"]
        char = event["ocr_unit"] if kind == "insertion" else event["ground_truth_unit"]
        row = by_char.setdefault(
            char, dict(**character_identity(char), total=0, substitution=0, deletion=0, insertion=0)
        )
        row[kind] += 1
        row["total"] += 1
        if kind == "substitution":
            pairs[(event["ground_truth_unit"], event["ocr_unit"])] += 1
    return dict(
        character_edits=len(events),
        substitution=counts["substitution"],
        deletion=counts["deletion"],
        insertion=counts["insertion"],
        gt_characters=len(reference),
        characters=sorted(by_char.values(), key=lambda r: (-r["total"], r["character"])),
        confusion_pairs=[
            dict(expected=a, predicted=b, count=n) for (a, b), n in pairs.most_common()
        ],
        events=events,
    )
