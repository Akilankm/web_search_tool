from __future__ import annotations

from pathlib import Path

from src.product_evidence_harness.runtime_contract import RUNTIME_CONTRACT_VERSION


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "MANAGEMENT_DEMO_GUIDE.md"


def test_management_demo_guide_is_complete_and_speaker_ready() -> None:
    assert GUIDE.is_file()
    text = GUIDE.read_text(encoding="utf-8")

    required_sections = (
        "Executive opening",
        "Business problem",
        "Management value",
        "Input and feature contract",
        "End-to-end architecture",
        "Processing workflow and business judgments",
        "Human-comparable decision artifact",
        "Artifacts",
        "Performance, latency, tokens and cost",
        "Recommended KPIs",
        "Assumptions",
        "Constraints and non-goals",
        "Failure handling",
        "Change-impact map",
        "Demo script",
        "Pre-demo checklist and metric card",
        "Leadership questions",
        "Leadership decisions for scale",
    )
    for section in required_sections:
        assert section in text


def test_management_guide_matches_current_business_contract() -> None:
    text = GUIDE.read_text(encoding="utf-8")

    for token in (
        RUNTIME_CONTRACT_VERSION,
        "structured_no_url_review_outcome",
        "NO_SAFE_DIRECT_PRODUCT_URL_FOUND",
        "manufacturer_primary",
        "requested_retailer_country",
        "country_alternative",
        "global_fallback",
        "primary_url",
        "manufacturer_url",
        "retailer_url",
        "source_selection",
        "business_judgement_review.md",
        "visual_evidence_summary_df",
        "COMPLETED",
        "REVIEW_REQUIRED",
        "FAILED",
    ):
        assert token in text


def test_management_guide_does_not_present_limits_as_measured_usage() -> None:
    text = GUIDE.read_text(encoding="utf-8")

    assert "These are limits, not actual usage" in text
    assert "fixed SLA must not be claimed" in text
    assert "LLM_MAX_TOKENS` is a response ceiling, not actual usage" in text
    assert "per-product summary" in text
    assert "execution_metrics.json" in text
    assert "llm_usage.json" in text


def test_canonical_docs_link_the_management_guide() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    final_contract = (ROOT / "docs" / "FINAL_SYSTEM_CONTRACT.md").read_text(
        encoding="utf-8"
    )

    assert "docs/MANAGEMENT_DEMO_GUIDE.md" in readme
    assert "MANAGEMENT_DEMO_GUIDE.md" in final_contract
