"""Generate synthetic documents. A Thai-capable font must be supplied."""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def generate(destination, font_path):
    destination.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(font_path), 27)
    small = ImageFont.truetype(str(font_path), 21)
    records = []

    def save(name, image, expected, kind, format="PNG"):
        path = destination / f"{name}.{format.lower()}"
        image.save(path, format=format)
        records.append(
            {
                "name": name,
                "file": path.name,
                "category": kind,
                "expected_text": expected,
                "width": image.width,
                "height": image.height,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )

    def text_image(text, size=(800, 220)):
        image = Image.new("RGB", size, "white")
        ImageDraw.Draw(image).multiline_text(
            (30, 35), text, font=font, fill="black", spacing=14
        )
        return image

    english = text_image("Document 123\nHello world")
    save("english", english, "Document 123\nHello world", "english")
    save(
        "thai",
        text_image("ภาษาไทย ทดสอบเอกสาร\nกรุงเทพมหานคร 123"),
        "ภาษาไทย ทดสอบเอกสาร\nกรุงเทพมหานคร 123",
        "thai",
    )
    save(
        "mixed",
        text_image("ใบแจ้งหนี้ Invoice 2026\nรวม Total 250 บาท"),
        "ใบแจ้งหนี้ Invoice 2026\nรวม Total 250 บาท",
        "mixed",
    )
    save("english_jpeg", english, "Document 123\nHello world", "english", "JPEG")
    save("english_webp", english, "Document 123\nHello world", "english", "WEBP")
    save("crop", english.crop((20, 20, 500, 90)), "Document 123", "crop")
    save(
        "rotated",
        english.rotate(90, expand=True),
        "Document 123\nHello world",
        "rotated_90",
    )
    save(
        "skewed",
        english.rotate(6, expand=True, fillcolor="white"),
        "Document 123\nHello world",
        "skewed_6_degrees",
    )
    save(
        "blurred",
        english.resize((400, 110)).filter(ImageFilter.GaussianBlur(1.2)),
        "Document 123\nHello world",
        "blur_low_resolution",
    )
    save("blank", Image.new("RGB", (800, 220), "white"), "", "blank")
    for name, size in [
        ("resolution_small", (400, 200)),
        ("resolution_medium", (800, 400)),
        ("resolution_large", (1200, 800)),
    ]:
        save(name, text_image("Benchmark 789", size), "Benchmark 789", "resolution")
    page = Image.new("RGB", (1000, 1400), "white")
    draw = ImageDraw.Draw(page)
    draw.text((50, 50), "SYNTHETIC REPORT 2026", font=font, fill="black")
    for row in range(10):
        draw.text(
            (50, 130 + row * 90),
            f"Section {row + 1}: Document processing and evaluation.",
            font=small,
            fill="black",
        )
    save("full_page", page, "SYNTHETIC REPORT 2026", "full_page")
    table = Image.new("RGB", (800, 450), "white")
    draw = ImageDraw.Draw(table)
    values = [
        ["Item", "Quantity", "Price"],
        ["Notebook", "2", "100"],
        ["Pen", "3", "50"],
        ["Total", "5", "150"],
    ]
    for y, row in enumerate(values):
        for x, value in enumerate(row):
            box = (30 + x * 240, 30 + y * 90, 270 + x * 240, 120 + y * 90)
            draw.rectangle(box, outline="black", width=2)
            draw.text((box[0] + 10, box[1] + 20), value, font=small, fill="black")
    save("table", table, "Notebook", "table")
    complex_table = table.copy()
    draw = ImageDraw.Draw(complex_table)
    draw.rectangle((30, 30, 510, 120), fill="white", outline="black", width=2)
    draw.text((45, 55), "Merged heading", font=small, fill="black")
    save("complex_table", complex_table, "Merged heading", "complex_table")
    save(
        "invoice",
        text_image("INVOICE 42\nNotebook 2 x 50 = 100\nTax 7\nTOTAL 107", (800, 350)),
        "INVOICE 42",
        "invoice",
    )
    columns = Image.new("RGB", (1000, 600), "white")
    draw = ImageDraw.Draw(columns)
    draw.multiline_text(
        (30, 40),
        "LEFT COLUMN\nAlpha 123\nBeta 456",
        font=font,
        fill="black",
        spacing=30,
    )
    draw.multiline_text(
        (530, 40),
        "RIGHT COLUMN\nGamma 789\nDelta 012",
        font=font,
        fill="black",
        spacing=30,
    )
    save("multicolumn", columns, "LEFT COLUMN", "multicolumn")
    save("formula", text_image("Mathematics\nx² + y² = z²\nE = mc²"), "x", "formula")
    chart = Image.new("RGB", (800, 500), "white")
    draw = ImageDraw.Draw(chart)
    draw.text((50, 25), "Synthetic Sales Chart", font=font, fill="black")
    draw.line((70, 100, 70, 400, 730, 400), fill="black", width=3)
    for x, height, label in [(150, 100, "A"), (330, 230, "B"), (510, 170, "C")]:
        draw.rectangle((x, 400 - height, x + 100, 400), fill="gray", outline="black")
        draw.text((x + 30, 420), label, font=small, fill="black")
    save("chart", chart, "Synthetic Sales Chart", "chart")
    (destination / "corrupt.png").write_bytes(b"not a decodable synthetic image")
    records.append(
        {
            "name": "corrupt",
            "file": "corrupt.png",
            "category": "corrupted",
            "expected_error": "INVALID_IMAGE",
        }
    )
    (destination / "manifest.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--font",
        required=True,
        type=Path,
        help="Thai-capable TTF; font is not redistributed",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "tests" / "fixtures")
    args = parser.parse_args()
    generate(args.output, args.font)
