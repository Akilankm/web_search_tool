from __future__ import annotations

from pathlib import Path

from src.product_evidence_harness.runtime_contract import RUNTIME_CONTRACT_VERSION


ROOT = Path(__file__).resolve().parents[1]
FEATURE_REFERENCE = ROOT / "docs" / "FEATURE_REFERENCE.md"
WORKFLOW = ROOT / "docs" / "SYSTEM_WORKFLOW.md"
UI_DOC = ROOT / "docs" / "PRODUCT_EVIDENCE_UI.md"


def test_feature_reference_covers_platform_features() -> None:
    text = FEATURE_REFERENCE.read_text(encoding="utf-8")
    for section in (
        "Product input contract",
        "Product interpretation",
        "Feature schema resolution",
        "Adaptive source search",
        "Candidate normalization and precision filtering",
        "Static extraction",
        "Rendered browser investigation",
        "Multimodal evidence reasoning",
        "Exact-product identity verification",
        "Requested-feature coverage",
        "URL durability and usability",
        "Source-authority selection",
        "Structured no-safe-URL outcome",
        "Business judgment sequence",
        "Per-job runtime controls",
        "Product Evidence Platform UI",
        "Batch execution",
        "Artifact diagnostics",
        "Artifact inventory",
        "Change-impact index",
    ):
        assert section in text


def test_feature_reference_maps_features_to_modules_and_outputs() -> None:
    text = FEATURE_REFERENCE.read_text(encoding="utf-8")
    for token in (
        "Primary modules",
        "Requirement changes",
        "Outputs",
        "business_judgement_review.md",
        "run_configuration.json",
        "apps/product_evidence_ui.py",
        "src/product_evidence_harness/runtime_controls.py",
        "NO_SAFE_DIRECT_PRODUCT_URL_FOUND",
        "Latency Optimized",
        "Coverage Optimized",
    ):
        assert token in text


def test_workflow_and_ui_docs_match_current_runtime() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    ui = UI_DOC.read_text(encoding="utf-8")
    assert RUNTIME_CONTRACT_VERSION == "belief-url-resolution-v9-product-evidence-ui"
    assert RUNTIME_CONTRACT_VERSION in ui
    for token in (
        "Product interpretation",
        "Adaptive source search",
        "Rendered browser investigation",
        "Exact-product verification",
        "Source-authority selection",
        "Decision audit sequence",
        "Runtime control flow",
    ):
        assert token in workflow


def test_canonical_docs_use_professional_terminology() -> None:
    paths = (
        ROOT / "README.md",
        FEATURE_REFERENCE,
        WORKFLOW,
        UI_DOC,
        ROOT / "docs" / "FINAL_SYSTEM_CONTRACT.md",
        ROOT / "docs" / "AZUREML_OPERATIONS.md",
        ROOT / "docs" / "NOTEBOOK_USAGE.md",
        ROOT / "docs" / "BUSINESS_JUDGEMENT_REVIEW.md",
        ROOT / "docs" / "STRUCTURED_NO_URL_OUTCOME.md",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        for forbidden in ("leadership", "management", "fast demo", "deep evidence demo"):
            assert forbidden not in text, f"{forbidden!r} found in {path}"
