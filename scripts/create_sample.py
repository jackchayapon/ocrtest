"""Generate a synthetic, non-personal document fixture for local UI testing."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[1]
output = root / "frontend" / "public" / "sample-document.png"
output.parent.mkdir(parents=True, exist_ok=True)
image = Image.new("RGB", (1000, 1320), "white")
draw = ImageDraw.Draw(image)
font_path = next((p for p in [Path("C:/Windows/Fonts/tahoma.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")] if p.exists()), None)


def font(size):
    return ImageFont.truetype(str(font_path), size) if font_path else ImageFont.load_default(size=size)


draw.rectangle((0, 0, 1000, 12), fill="#6256df")
draw.text((80, 76), "OCR LAB", fill="#6256df", font=font(34))
draw.text((80, 135), "SYNTHETIC BENCHMARK DOCUMENT", fill="#8b8f9c", font=font(17))
draw.line((80, 200, 920, 200), fill="#e0e2e8", width=2)
draw.text((80, 245), "บริษัท ซีดีจี จำกัด", fill="#232b3d", font=font(40))
draw.text((80, 317), "Thai text recognition sample", fill="#9297a3", font=font(19))
draw.text((80, 409), "REFERENCE DETAILS", fill="#6256df", font=font(17))
for i, (label, value) in enumerate([("Document", "OCR-DEMO-001"), ("Content", "Thai / English / Numbers"), ("Purpose", "Testing only — no personal data")]):
    y = 467 + i * 65
    draw.text((80, y), label, fill="#969aa6", font=font(20))
    draw.text((315, y), value, fill="#41485a", font=font(21))
draw.rounded_rectangle((80, 708, 920, 974), radius=10, fill="#f7f7fc", outline="#e8e7ef", width=2)
draw.text((110, 746), "Numbers & mixed content", fill="#525971", font=font(22))
draw.text((110, 805), "0123456789       ๐๑๒๓๔๕๖๗๘๙", fill="#252e42", font=font(30))
draw.text((110, 875), "Invoice 001  /  จำนวน 125.50 บาท", fill="#626b7e", font=font(25))
draw.line((80, 1080, 920, 1080), fill="#e0e2e8", width=2)
draw.text((80, 1117), "Select a region around the Thai heading to begin.", fill="#8a91a0", font=font(19))
draw.text((80, 1160), "Mock pipelines return fixtures; real mode requires Gateway access.", fill="#a2a7b1", font=font(17))
image.save(output, format="PNG")
print(output)
