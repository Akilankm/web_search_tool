from __future__ import annotations

from pathlib import Path

from src.product_evidence_harness.runtime_contract import RUNTIME_CONTRACT_VERSION


ROOT = Path(__file__).resolve().parents[1]
FEATURE_REFERENCE = ROOT / "docs" / "FEATURE_REFERENCE.md"
WORKFLOW = ROOT / "docs" / "SYSTEM_WORKFLOW.md"
UI_DOC = ROOT / "docs" / "PRODUCT_EVIDENCE_UI.md"


def test_feature_reference_covers_product_evidence_features() -> None:
    text = FEATURE_REFERENCE.read_text(encoding="utf-8")
    for section in (
        "Product input contract",
        "Product interpretation",
        "Product hypothesis construction",
        "Feature schema resolution",
        "Adaptive source search",
        "Candidate normalization and precision filtering",
        "Static extraction",
        "Rendered browser investigation",
        "Multimodal evidence reasoning",
        "Evidence ledger",
        "Hypothesis scoring and product resolution",
        "Exact-product identity verification",
        "Requested-feature coverage",
        "URL durability and usability",
        "Source-authority selection",
        "Structured no-safe-URL outcome",
        "Business judgment sequence",
        "Per-job runtime controls",
        "Product Identification Platform UI",
        "Batch execution",
        "Artifact diagnostics",
        "Artifact inventory",
        "Change-impact index",
    ):
        assert section in text


def test_ui_document_enforces_decision_first_url_hierarchy() -> None:
    text = UI_DOC.read_text(encoding="utf-8")
    for token in (
        "Product URL Decision UI",
        "Primary outcome",
        "justifiable product URL",
        "Decision-first result hierarchy",
        "Source",
        "Evidence",
        "Identity",
        "Usability",
        "No justifiable URL",
        "Search work completed",
        "Candidate URL decisions",
        "Review evidence and decision details",
        "executive_summary.json",
        "Fast",
        "Standard",
        "Deep review",
    ):
        assert token in text


def test_workflow_and_ui_docs_match_runtime_contract() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    ui = UI_DOC.read_text(encoding="utf-8")
    assert RUNTIME_CONTRACT_VERSION == "belief-url-resolution-v10-decision-first-ui"
    assert RUNTIME_CONTRACT_VERSION in ui
    for token in (
        "Product interpretation",
        "Product hypothesis construction",
        "Adaptive source search",
        "Rendered browser investigation",
        "Exact-product verification",
        "Product identity resolution",
        "Source-authority selection",
        "Decision audit sequence",
        "Runtime control flow",
    ):
        assert token in workflow
    for token in (
        "Primary outcome",
        "JUSTIFIABLE_URL_FOUND",
        "URL_FOUND_REVIEW_REQUIRED",
        "NO_JUSTIFIABLE_URL_FOUND",
        "executive_url_decision_summary=true",
    ):
        assert token in ui


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
