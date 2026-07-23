from pathlib import Path

import nbformat


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_CODE = (
    "product_evidence_harness",
    "compat_patches",
    "monkey_patch",
    "monkeypatch_runtime",
    "nest_asyncio",
    "product_url_v2.api",
    "browser_service",
)


def test_no_legacy_service_or_monkey_patch_code() -> None:
    offenders = []

    for folder in (ROOT / "src", ROOT / "scripts"):
        for file in folder.rglob("*"):
            if not file.is_file() or file.suffix not in {".py", ".sh"}:
                continue
            text = file.read_text(encoding="utf-8", errors="ignore")
            if any(token in text for token in FORBIDDEN_CODE):
                offenders.append(str(file.relative_to(ROOT)))

    for notebook_path in (ROOT / "notebooks").glob("*.ipynb"):
        notebook = nbformat.read(notebook_path, as_version=4)
        code = "\n".join(
            str(cell.source) for cell in notebook.cells if cell.cell_type == "code"
        )
        if any(token in code for token in FORBIDDEN_CODE):
            offenders.append(str(notebook_path.relative_to(ROOT)))

    assert not offenders, offenders
