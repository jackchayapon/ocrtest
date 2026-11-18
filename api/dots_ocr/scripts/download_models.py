"""Download pinned official snapshots without using a stored Hugging Face token."""

import argparse
import json
import sys
from pathlib import Path

import requests
from huggingface_hub import configure_http_backend, snapshot_download

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def direct_session():
    session = requests.Session()
    session.trust_env = False
    return session


def main():
    from app.integrity import verify_snapshot

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "model", choices=["dots-studio/dots.ocr", "dots-studio/dots.mocr"]
    )
    parser.add_argument("--root", type=Path, default=ROOT / "models")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "model-manifest.json").read_text())
    entry = manifest[args.model]
    target = args.root.resolve() / entry["directory"]
    configure_http_backend(direct_session)
    snapshot_download(
        args.model,
        revision=entry["revision"],
        local_dir=target,
        token=False,
        max_workers=2,
    )
    verify_snapshot(target, entry)
    (target / "snapshot-identity.json").write_text(
        json.dumps({"model": args.model, "revision": entry["revision"]})
    )
    print(
        json.dumps(
            {
                "model": args.model,
                "revision": entry["revision"],
                "directory": str(target),
                "downloaded_bytes": sum(
                    p.stat().st_size for p in target.rglob("*") if p.is_file()
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
