from pathlib import Path


def test_no_legacy_or_monkey_patch_references() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = ("product_evidence_harness", "compat_patches", "monkey_patch", "monkeypatch_runtime")
    scan = [root / "src", root / "apps", root / "scripts", root / "docker", root / "docs", root / "README.md", root / "pyproject.toml", root / "docker-compose.yml"]
    offenders = []
    for path in scan:
        files = [path] if path.is_file() else [item for item in path.rglob("*") if item.is_file()]
        for file in files:
            text = file.read_text(encoding="utf-8", errors="ignore")
            if any(token in text for token in forbidden):
                offenders.append(str(file.relative_to(root)))
    assert not offenders, offenders
