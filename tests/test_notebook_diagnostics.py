from __future__ import annotations

from pathlib import Path

import pandas as pd

from product_evidence_harness.notebook_diagnostics import (
    build_single_product_diagnostics,
)


def _write_candidate_artifacts(root: Path) -> None:
    pd.DataFrame(
        [
            {
                "url": "https://shop.example/product-a",
                "source_types": "organic|scope_requested_retailer_country",
                "best_position": "1",
                "confidence": "0.96",
                "validation_status": "VERIFIED",
                "identity_status": "VERIFIED",
                "ean_check": "MATCHED",
                "title_check": "STRONG",
                "page_type": "PRODUCT_PAGE",
                "scrapable": "True",
                "richness": "0.88",
                "decision_reasons": "exact product|full evidence",
            },
            {
                "url": "https://other.example/listing",
                "source_types": "organic|scope_global_fallback",
                "best_position": "4",
                "confidence": "0.42",
                "validation_status": "REVIEW",
                "identity_status": "REJECTED",
                "ean_check": "UNKNOWN",
                "title_check": "WEAK",
                "page_type": "PRODUCT_PAGE",
                "scrapable": "True",
                "richness": "0.35",
                "decision_reasons": "variant conflict|weak title",
            },
            {
                "url": "https://blocked.example/item",
                "source_types": "organic|scope_country_alternative",
                "best_position": "2",
                "confidence": "0.10",
                "validation_status": "REJECTED",
                "identity_status": "NOT_SCRAPED",
                "ean_check": "UNKNOWN",
                "title_check": "UNKNOWN",
                "page_type": "UNKNOWN",
                "scrapable": "False",
                "richness": "0",
                "decision_reasons": "access blocked",
            },
        ]
    ).to_csv(root / "candidates.csv", index=False)

    pd.DataFrame(
        [
            {
                "url": "https://shop.example/product-a",
                "source_role": "primary",
                "identity_status": "VERIFIED",
                "feature_id": "brand",
                "feature_name": "Brand",
                "value": "Example",
                "status": "EXPLICITLY_FOUND",
                "confidence": "0.99",
                "evidence_location": "specification table",
                "evidence_text": "Brand: Example",
                "extraction_method": "deterministic",
            },
            {
                "url": "https://shop.example/product-a",
                "source_role": "primary",
                "identity_status": "VERIFIED",
                "feature_id": "age",
                "feature_name": "Minimum age",
                "value": "3 years",
                "status": "STRUCTURED_FOUND",
                "confidence": "0.95",
                "evidence_location": "json-ld",
                "evidence_text": "3+",
                "extraction_method": "structured",
            },
        ]
    ).to_csv(root / "feature_evidence.csv", index=False)


def _result() -> dict:
    return {
        "job_status": "COMPLETED",
        "coding_ready": True,
        "product": {
            "row_id": "ROW-001",
            "main_text": "Example Product",
            "country_code": "CH",
            "retailer_name": "Example Shop",
            "ean": "123",
        },
        "search": {
            "serpapi_requests_used": 3,
            "stages": [
                {
                    "serp_credit": 1,
                    "name": "requested_retailer_country",
                    "scope": "country",
                    "query": "query one",
                    "language_code": "de",
                    "results_returned": 10,
                    "new_candidate_urls": 3,
                    "candidates_scraped": 1,
                },
                {
                    "serp_credit": 2,
                    "name": "country_alternative",
                    "scope": "country",
                    "query": "query two",
                    "language_code": "de",
                    "results_returned": 8,
                    "new_candidate_urls": 2,
                    "candidates_scraped": 1,
                },
                {
                    "serp_credit": 3,
                    "name": "global_fallback",
                    "scope": "global",
                    "query": "query three",
                    "language_code": "en",
                    "results_returned": 12,
                    "new_candidate_urls": 1,
                    "candidates_scraped": 1,
                },
            ],
        },
        "candidate_investigations": [
            {
                "candidate_id": "CAND-001",
                "requested_url": "https://shop.example/product-a",
                "final_url": "https://shop.example/product-a",
                "status": "COMPLETED",
                "turns_used": 3,
                "actions_executed": 2,
                "termination_reason": "LLM_FINISHED_INVESTIGATION",
                "final_llm_assessment": {"exact_product": True},
                "error": None,
            },
            {
                "candidate_id": "CAND-002",
                "requested_url": "https://other.example/listing",
                "final_url": "https://other.example/listing",
                "status": "COMPLETED",
                "turns_used": 2,
                "actions_executed": 1,
                "termination_reason": "WRONG_VARIANT",
                "final_llm_assessment": {"exact_product": False},
                "error": None,
            },
        ],
        "browser_evidence": [
            {
                "requested_url": "https://shop.example/product-a",
                "browser_openable": True,
                "rendered_product_verified": True,
                "text_scrapable": True,
                "multimodal_scrapable": True,
                "gallery_discovered": True,
                "direct_images_downloaded": 4,
                "screenshots_captured": 2,
                "blockers": [],
                "warnings": [],
                "error": None,
            },
            {
                "requested_url": "https://other.example/listing",
                "browser_openable": True,
                "rendered_product_verified": False,
                "text_scrapable": True,
                "multimodal_scrapable": False,
                "gallery_discovered": False,
                "direct_images_downloaded": 0,
                "screenshots_captured": 1,
                "blockers": [],
                "warnings": ["variant mismatch"],
                "error": None,
            },
        ],
        "feature_assessments": [
            {
                "url": "https://shop.example/product-a",
                "identity_accepted": True,
                "identity_status": "VERIFIED",
                "source_role": "primary",
                "coverage": 1.0,
                "required_coverage": 1.0,
                "critical_coverage": 1.0,
                "missing_features": [],
                "conflicting_features": [],
                "rejection_reasons": [],
                "evidence": [
                    {
                        "feature_id": "brand",
                        "feature_name": "Brand",
                        "value": "Example",
                        "status": "EXPLICITLY_FOUND",
                        "confidence": 0.99,
                        "evidence_location": "specification table",
                        "extraction_method": "deterministic",
                        "evidence_text": "Brand: Example",
                    },
                    {
                        "feature_id": "age",
                        "feature_name": "Minimum age",
                        "value": "3 years",
                        "status": "STRUCTURED_FOUND",
                        "confidence": 0.95,
                        "evidence_location": "json-ld",
                        "extraction_method": "structured",
                        "evidence_text": "3+",
                    },
                ],
            },
            {
                "url": "https://other.example/listing",
                "identity_accepted": False,
                "identity_status": "REJECTED",
                "source_role": "supplementary",
                "coverage": 0.5,
                "required_coverage": 0.5,
                "critical_coverage": 0.0,
                "missing_features": ["age"],
                "conflicting_features": ["brand"],
                "rejection_reasons": ["variant conflict"],
                "evidence": [],
            },
        ],
        "primary_url": "https://shop.example/product-a",
        "supplementary_urls": [],
        "primary_url_acceptance": {
            "accepted": True,
            "primary_url": "https://shop.example/product-a",
            "reasons": [],
        },
        "evidence_set": {
            "selected_urls": ["https://shop.example/product-a"],
            "status": "CODING_READY_STRICT_PRIMARY_URL",
            "total_coverage": 1.0,
            "missing_features": [],
            "conflicting_features": [],
        },
        "product_match": {
            "url_decision_status": "STRICT_AGENTIC_PRIMARY_URL_ACCEPTED",
            "selection_scope": "REQUESTED_RETAILER_COUNTRY",
            "identity_status": "VERIFIED",
            "validation_status": "VERIFIED",
            "confidence": 0.96,
        },
    }


def test_single_product_diagnostics_builds_candidate_funnel_and_rca(tmp_path: Path) -> None:
    _write_candidate_artifacts(tmp_path)

    diagnostics = build_single_product_diagnostics(_result(), artifact_dir=tmp_path)

    assert len(diagnostics.results_df) == 3
    assert diagnostics.results_df.iloc[0]["final_candidate_status"] == "STRICT_SELECTED"
    assert diagnostics.results_df["scrape_attempted"].sum() == 2
    assert diagnostics.results_df["scrape_success"].sum() == 2
    assert diagnostics.results_df["agentic_investigated"].sum() == 2
    assert diagnostics.results_df["identity_accepted"].sum() == 1
    assert diagnostics.results_df["feature_complete"].sum() == 1

    funnel = diagnostics.funnel_df.set_index("stage")["count"].to_dict()
    assert funnel["SERP rows returned"] == 30
    assert funnel["Unique candidate URLs"] == 3
    assert funnel["Selected"] == 1

    assert set(diagnostics.feature_matrix_df.columns) == {"Brand", "Minimum age"}
    assert not diagnostics.rejection_reasons_df.empty
    assert "variant conflict" in set(diagnostics.rejection_reasons_df["reason"])
    assert (
        diagnostics.selection_rca_df.set_index("RCA item").loc[
            "Chosen primary URL", "value"
        ]
        == "https://shop.example/product-a"
    )


def test_diagnostics_falls_back_to_persisted_candidate_inventory(tmp_path: Path) -> None:
    _write_candidate_artifacts(tmp_path)
    result = _result()
    result["search"].pop("serp_results", None)

    diagnostics = build_single_product_diagnostics(result, artifact_dir=tmp_path)

    assert len(diagnostics.serp_results_df) == 3
    assert set(diagnostics.serp_results_df["record_type"]) == {
        "deduplicated_candidate"
    }
    assert diagnostics.serp_results_df["url"].nunique() == 3
