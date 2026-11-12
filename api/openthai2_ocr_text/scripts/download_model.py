"""Provision a pinned public runtime/weight snapshot without executing it."""
import argparse
import hashlib
import json
from pathlib import Path

import httpx

REVISION = "39fa41bdd49f067ba41b1d9de79c06ab506d67d4"
FILES = ["det.onnx", "rec.onnx", "det.yml", "rec_dict.txt", "config.json",
         "runtime/__init__.py", "runtime/line_engine.py", "runtime/thai_norm.py", "README.md", "NOTICE"]
# The pinned revision's SHA256SUMS predates its README edit. Verify that document
# against the independently reviewed revision content, while keeping all model
# and runtime checksums from the upstream manifest mandatory.
README_SHA256 = "4738dea47f1d31454fbb6632460560927725388e70026137fa0f162c71e7329e"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("models/openthai2"))
    args = parser.parse_args()
    base = f"https://huggingface.co/iapp/OpenThai2.0-OCR-Text/resolve/{REVISION}/"
    manifest = {}
    locked = json.loads((Path(__file__).resolve().parents[1] / "model-manifest.json").read_text())
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        sums = client.get(base + "SHA256SUMS").raise_for_status().text
        expected = {line.split()[-1].removeprefix("./"): line.split()[0] for line in sums.splitlines() if line.strip()}
        for name in FILES:
            content = client.get(base + name).raise_for_status().content
            digest = hashlib.sha256(content).hexdigest()
            wanted = README_SHA256 if name == "README.md" else expected.get(name)
            if wanted is None or wanted != digest or locked["sha256"].get(name) != digest:
                raise ValueError("Upstream checksum mismatch for " + name)
            target = args.output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            manifest[name] = digest
        (args.output / "SHA256SUMS").write_text(sums)
    (args.output / "provisioned.json").write_text(json.dumps({"revision": REVISION, "sha256": manifest}, indent=2))
    print(json.dumps({"revision": REVISION, "files": len(manifest), "bytes": sum((args.output / f).stat().st_size for f in manifest)}))


if __name__ == "__main__":
    main()
