import hashlib
from pathlib import Path


def verify_snapshot(directory, entry):
    """Verify pinned HF Git blobs/LFS SHA-256 before executing custom model code."""
    directory = Path(directory)
    expected = entry["files"]
    actual_code = {p.relative_to(directory).as_posix() for p in directory.glob("*.py")}
    if actual_code != {name for name in expected if name.endswith(".py")}:
        raise ValueError("Unexpected snapshot code")
    for name, specification in expected.items():
        path = directory / name
        if path.is_symlink() or path.stat().st_size != specification["size"]:
            raise ValueError("Snapshot file size or path mismatch")
        git_blob = specification["algorithm"] == "git-blob-sha1"
        digest = hashlib.sha1() if git_blob else hashlib.sha256()
        if git_blob:
            digest.update(f"blob {specification['size']}\0".encode())
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != specification["hash"]:
            raise ValueError("Snapshot integrity mismatch")
