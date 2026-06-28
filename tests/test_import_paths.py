from __future__ import annotations

from pathlib import Path


def test_internal_imports_do_not_use_src_package_prefix() -> None:
    root = Path(__file__).resolve().parents[1]
    python_files = list((root / 'src').rglob('*.py')) + [root / 'main.py', root / 'batch_main.py']
    offenders: list[str] = []
    for path in python_files:
        text = path.read_text(encoding='utf-8')
        if 'src.product_evidence_harness' in text or 'from src.' in text or 'import src.' in text:
            offenders.append(str(path.relative_to(root)))
    assert not offenders, f'Invalid src-prefixed package imports found: {offenders}'


def test_public_package_imports_from_src_path() -> None:
    import product_evidence_harness as peh

    assert hasattr(peh, 'ProductEvidenceHarness')
    assert hasattr(peh, 'HarnessConfig')
    assert hasattr(peh, 'ProductQuery')
