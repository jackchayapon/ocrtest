from pathlib import Path

from packaging.requirements import Requirement


def test_production_runtime_lock_covers_application_requirements():
    root = Path(__file__).resolve().parents[1]
    locked = {
        requirement.name.lower(): next(iter(requirement.specifier)).version
        for line in (root / "requirements-runtime-lock.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
        for requirement in [Requirement(line)]
    }
    development_only = {"pytest", "ruff"}
    for line in (root / "requirements.txt").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        requirement = Requirement(line)
        if requirement.name.lower() in development_only:
            continue
        assert requirement.name.lower() in locked, f"Missing production dependency: {requirement.name}"
        assert requirement.specifier.contains(locked[requirement.name.lower()])
    assert "-r requirements-runtime-lock.txt" in (root / "requirements-lock.txt").read_text()
    assert "pip install --no-cache-dir -r requirements-runtime-lock.txt" in (root / "Dockerfile").read_text()
