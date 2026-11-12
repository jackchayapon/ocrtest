"""Exercise a running model over actual HTTP using generated public test input."""
import argparse
import io
import json
import os

import httpx
from PIL import Image, ImageDraw, ImageFont


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8091")
    parser.add_argument("--font", help="Path to a Thai-capable font, for example Tahoma or Noto Sans Thai")
    args = parser.parse_args()
    headers = {"X-API-Key": os.environ["OPENTHAI_API_KEY"]} if os.environ.get("OPENTHAI_API_KEY") else {}
    report = []
    with httpx.Client(base_url=args.url, headers=headers, timeout=120, follow_redirects=False) as client:
        client.get("/health").raise_for_status()
        client.get("/api/v1/readiness").raise_for_status()
        for label, text in [("blank", ""), ("text", "ทดสอบภาษาไทย 123\nOpenThai OCR 2026" if args.font else "OpenThai OCR 2026")]:
            with Image.new("RGB", (780, 250), "white") as image, io.BytesIO() as output:
                font = ImageFont.truetype(args.font, 42) if args.font else ImageFont.load_default(size=42)
                ImageDraw.Draw(image).multiline_text((25, 30), text, fill="black", font=font, spacing=20)
                image.save(output, "PNG")
                response = client.post("/api/v1/ocr-text", files={"image": (label+".png", output.getvalue(), "image/png")})
            response.raise_for_status()
            payload = response.json()
            assert bool(payload["data"]["text"]) == bool(text)
            assert payload["data"]["confidence"] is None
            report.append({"case": label, "status": response.status_code, "characters": len(payload["data"]["text"]),
                           "lines": len(payload["data"]["lines"]), "meta": payload["meta"]})
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
