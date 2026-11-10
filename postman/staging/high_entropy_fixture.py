"""Generate only the public synthetic40MP counterexample; no environment/network access."""
import argparse
import hashlib
import io
from contextlib import closing
from pathlib import Path

import numpy as np
from PIL import Image

EXPECTED_SHA256 = "264c0b9576405f17896b0db096649f7743ceebc68a872360ea599596a32f936d"


def fixture_bytes():
    rng = np.random.default_rng(20261109)
    with closing(Image.new("RGB", (8000, 5000))) as image:
        for y in range(0, 5000, 100):
            with closing(Image.fromarray(rng.integers(0, 256, (100, 8000, 3), dtype=np.uint8))) as tile:
                image.paste(tile, (0, y))
        with io.BytesIO() as output:
            image.save(output, format="JPEG", quality=30)
            return output.getvalue()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional new local file; existing files are never overwritten")
    args = parser.parse_args()
    data = fixture_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit("Fixture encoding differs from reference; do not compare measurements as identical inputs")
    if args.output:
        with args.output.open("xb") as target:
            target.write(data)
    print(f"8000x5000 RGB JPEG; bytes={len(data)}; sha256={digest}")
