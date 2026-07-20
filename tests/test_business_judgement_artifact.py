from __future__ import annotations

from pathlib import Path

from src.product_evidence_harness.business_judgement_artifact import (
    ARTIFACT_FILENAME,
    SCHEMA_VERSION,
    build_business_judgement_review,
    write_business_judgement_review,
)


def _result(tmp_path: Path) -> dict:
    manufacturer = "https://www.lego.com/en-gb/product/r2-d2-75379"
    retailer = "https://www.amazon.co.uk/dp/B0ABC12345"
    return {
        "job_status": "COMPLETED",
        "artifact_dir": str(tmp_path),
        "product": {
            "row_id": "ROW-JUDGMENT-1",
            "main_text": "LEGO Star Wars R2-D2 75379",
            "country_code": "GB",
            "retailer_name": "Amazon UK",
            "ean": "5702017584379",
            "language_code": "en",
        },
        "product_identification": {
            "resolution_status": "RESOLVED",
            "leading_hypothesis": {
                "canonical_name": "LEGO Star Wars R2-D2 75379",
                "posterior_probability": 0.96,
            },
            "uncertainties": ["Confirm exact set and package form"],
            "metrics": {"search_readiness": 0.94, "posterior_margin": 0.82},
        },
        "search": {
            "search_stage_order": [
                "manufacturer_primary",
                "requested_retailer_country",
                "global_fallback",
            ],
            "stages": [
                {
                    "serp_credit": 1,
                    "name": "manufacturer_primary",
                    "query": "LEGO R2-D2 75379 official manufacturer product page",
                    "results_returned": 10,
                    "new_candidate_urls": 3,
                    "candidates_qualified": 1,
                    "working_url_found": True,
                }
            ],
        },
        "candidate_investigations": [
            {
                "candidate_id": "CAND-001",
                "requested_url": manufacturer,
                "final_url": manufacturer,
                "status": "COMPLETED",
                "turns_used": 2,
                "actions_executed": 1,
                "termination_reason": "EXACT_PRODUCT_RESOLVED",
                "plans": [
                    {"action": "inspect_image"},
                    {"action": "finish"},
                ],
                "final_llm_assessment": {
                    "same_product": True,
                    "same_variant": True,
                    "product_page": True,
                    "confidence": 0.97,
                },
            }
        ],
        "browser_evidence": [
            {
                "requested_url": manufacturer,
                "final_url": manufacturer,
                "multimodal_scrapable": True,
                "gallery_discovered": True,
                "screenshots_captured": 2,
                "visual_assets": [{"asset_id": "IMG-1"}],
            }
        ],
        "feature_assessments": [
            {
                "url": manufacturer,
                "identity_accepted": True,
                "identity_status": "VERIFIED",
                "coverage": 1.0,
                "missing_features": [],
                "conflicting_features": [],
                "evidence": [
                    {
                        "feature_id": "colour",
                        "feature_name": "Colour",
                        "value": "Blue and white",
                        "extraction_method": "vision_llm",
                        "evidence_location": "visual_asset:IMG-1",
                    }
                ],
            }
        ],
        "primary_url": manufacturer,
        "primary_url_role": "OFFICIAL_MANUFACTURER",
        "manufacturer_url": manufacturer,
        "retailer_url": retailer,
        "primary_url_acceptance": {
            "accepted": True,
            "primary_url": manufacturer,
            "browser_openable": True,
            "text_scrapable": True,
            "rendered_product_verified": True,
            "exact_product_verified": True,
            "full_feature_coverage": True,
            "durable_url": True,
            "reasons": [],
        },
        "source_selection": {
            "policy": "MANUFACTURER_FIRST_AFTER_PRODUCTION_GATES",
            "selection_reason": "OFFICIAL_MANUFACTURER_PRIMARY_AFTER_STRICT_GATES",
            "source_tier_name": "LOCAL_MANUFACTURER",
        },
        "url_delivery": {
            "delivered": True,
            "strictly_verified": True,
            "status": "STRICTLY_VERIFIED",
        },
        "product_match": {"match_reason": "STRICT_AGENTIC_PRIMARY_URL_ACCEPTED"},
    }


def test_review_is_chronological_shareable_and_visually_explicit(tmp_path: Path) -> None:
    result = _result(tmp_path)
    review = build_business_judgement_review(result)

    assert review.schema_version == SCHEMA_VERSION
    assert len(review.steps) >= 7
    assert [step.sequence_number for step in review.steps] == list(
        range(1, len(review.steps) + 1)
    )
    assert review.steps[0].decision_stage == "INPUT_INTERPRETATION"
    assert review.steps[-1].decision_stage == "FINAL_DELIVERY"
    assert review.visual_evidence_summary["image_influenced_final_decision"] == (
        "YES_VISUAL_EVIDENCE_SUPPORTED_SELECTED_URL_FEATURE_GATE"
    )
    assert review.visual_evidence_summary["text_alone_would_have_passed"] == (
        "UNKNOWN_NOT_COUNTERFACTUALLY_TESTED"
    )

    markdown = review.markdown
    for required in (
        "# Business Judgment Review",
        "## Submitted input",
        "## Sequence of business judgments",
        "## Visual evidence impact",
        "## Human coder comparison form",
        "IDENTICAL",
        "PARTIALLY IDENTICAL",
        "NOT IDENTICAL",
        "First divergent step number",
        "LEGO Star Wars R2-D2 75379",
        "OFFICIAL_MANUFACTURER",
        "vision",
    ):
        assert required.lower() in markdown.lower()
    assert "does not expose hidden chain-of-thought" in markdown


def test_writer_attaches_result_contract_and_writes_markdown(tmp_path: Path) -> None:
    result = _result(tmp_path)
    payload = write_business_judgement_review(result, tmp_path)

    path = tmp_path / ARTIFACT_FILENAME
    assert path.is_file()
    assert result["business_judgement_review"] == payload
    assert payload["human_review_status"] == "PENDING_HUMAN_COMPARISON"
    assert payload["judgement_count"] == len(payload["steps"])
    assert payload["visual_evidence_summary"]["selected_url_features_resolved_visually"] == [
        "Colour"
    ]
    assert "Human coder comparison form" in path.read_text(encoding="utf-8")
