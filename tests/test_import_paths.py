from __future__ import annotations

import importlib


def test_public_package_imports_from_src_path() -> None:
    import product_evidence_harness as peh

    assert hasattr(peh, "ProductEvidenceHarness")
    assert hasattr(peh, "HarnessConfig")
    assert hasattr(peh, "ProductQuery")


def test_legacy_src_prefixed_namespace_resolves_for_existing_internal_imports() -> None:
    """Temporary compatibility check while generated imports are migrated.

    User-facing notebooks should import ``product_evidence_harness`` directly,
    but existing generated modules still contain legacy ``src.product...``
    imports. The compatibility namespace prevents ModuleNotFoundError when only
    ``<repo>/src`` is on sys.path.
    """
    mod = importlib.import_module("src.product_evidence_harness.config")
    assert hasattr(mod, "HarnessConfig")
