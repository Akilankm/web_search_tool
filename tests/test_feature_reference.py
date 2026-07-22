from __future__ import annotations

from pathlib import Path

from src.product_evidence_harness.runtime_contract import RUNTIME_CONTRACT_VERSION


ROOT = Path(__file__).resolve().parents[1]
FEATURE_REFERENCE = ROOT / "docs" / "FEATURE_REFERENCE.md"
WORKFLOW = ROOT / "docs" / "SYSTEM_WORKFLOW.md"
UI_DOC = ROOT / "docs" / "PRODUCT_EVIDENCE_UI.md"


def test_feature_reference_covers_url_delivery_features() -> None:
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
        "Strict URL selection",
        "Best-available review URL recovery",
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


def test_feature_reference_enforces_url_delivery_hierarchy() -> None:
    text = FEATURE_REFERENCE.read_text(encoding="utf-8")
    for token in (
        "Primary deliverable",
        "product URL",
        "URL_DELIVERED_VERIFIED",
        "URL_DELIVERED_REVIEW_REQUIRED",
        "URL_DELIVERY_FAILED",
        "confirmed wrong product",
        "confirmed wrong variant",
        "candidate_url_records.json",
        "candidate_state.json",
        "url_delivery_recovery.py",
        "apps/product_evidence_ui.py",
        "Focused",
        "Standard",
        "Extended",
    ):
        assert token in text


def test_workflow_and_ui_docs_match_runtime_contract() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    ui = UI_DOC.read_text(encoding="utf-8")
    assert RUNTIME_CONTRACT_VERSION == "belief-url-resolution-v11-url-delivery-first"
    assert RUNTIME_CONTRACT_VERSION in ui
    for token in (
        "Product interpretation",
        "Adaptive source search",
        "Rendered browser investigation",
        "Exact-product verification",
        "Source-authority selection",
        "Strict URL selection",
        "Best-available review URL recovery",
        "URL delivery",
        "Decision audit sequence",
        "Runtime control flow",
        "The UI must never present an empty URL as a successful or ordinary result",
    ):
        assert token in workflow
    for token in (
        "Primary deliverable",
        "best available review URL",
        "URL delivery failure",
        "exceptional escalation",
        "best_available_review_url_delivery=true",
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
