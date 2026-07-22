from __future__ import annotations

import json

from src.product_evidence_harness.executive_summary import (
    attach_executive_summary,
    build_executive_summary,
)


def _identity() -> dict:
    return {
        "resolution_status": "EXACT",
        "leading_hypothesis": {
            "hypothesis_id": "H-1",
            "canonical_name": "LEGO Star Wars R2-D2 75379",
            "posterior_probability": 0.96,
        },
        "hypotheses": [
            {
                "hypothesis_id": "H-1",
                "canonical_name": "LEGO Star Wars R2-D2 75379",
                "posterior_probability": 0.96,
                "contradicting_evidence_ids": [],
            }
        ],
        "claims": [
            {"field": "brand", "value": "LEGO", "status": "WEB_VERIFIED"},
            {"field": "model", "value": "75379", "status": "WEB_VERIFIED"},
        ],
        "evidence_ledger": [
            {
                "field": "model",
                "value": "75379",
                "polarity": "SUPPORTS",
                "source_url": "https://www.lego.com/product/75379",
            }
        ],
        "uncertainties": [],
        "unknowns": [],
    }


def test_executive_summary_prioritizes_delivered_url() -> None:
    result = {
        "job_status": "COMPLETED",
        "coding_ready": True,
        "product": {"row_id": "ROW-1", "main_text": "LEGO R2-D2 75379"},
        "product_identification": _identity(),
        "primary_url": "https://www.lego.com/product/75379",
        "manufacturer_url": "https://www.lego.com/product/75379",
        "retailer_url": None,
        "url_delivery": {
            "delivered": True,
            "strictly_verified": True,
            "url": "https://www.lego.com/product/75379",
        },
        "source_selection": {
            "source_role": "MANUFACTURER",
            "source_tier_name": "GLOBAL_MANUFACTURER",
            "selection_reason": "Official manufacturer page passed all production gates.",
        },
        "primary_url_acceptance": {
            "accepted": True,
            "browser_openable": True,
            "text_scrapable": True,
            "rendered_product_verified": True,
            "exact_product_verified": True,
            "full_feature_coverage": True,
            "durable_url": True,
            "reasons": ["EXACT_PRODUCT_IDENTITY", "DURABLE_URL"],
        },
        "evidence_set": {
            "required_coverage": 1.0,
            "critical_coverage": 1.0,
            "total_coverage": 1.0,
        },
        "search": {
            "serpapi_requests_used": 2,
            "serpapi_request_limit": 3,
            "stages": [
                {
                    "name": "manufacturer_primary",
                    "results_returned": 10,
                    "new_candidate_urls": 4,
                    "candidates_qualified": 2,
                    "candidates_scraped": 1,
                }
            ],
        },
        "browser_evidence": [
            {
                "requested_url": "https://www.lego.com/product/75379",
                "browser_openable": True,
                "text_scrapable": True,
                "visual_assets": [{"asset_id": "IMG-1"}],
            }
        ],
        "feature_assessments": [
            {
                "url": "https://www.lego.com/product/75379",
                "identity_status": "VERIFIED",
                "coverage": 1.0,
                "source_role": "MANUFACTURER",
            }
        ],
    }

    summary = build_executive_summary(result)

    assert summary["overall_status"] == "URL_DELIVERED_VERIFIED"
    assert summary["successful_output"] is True
    assert summary["selected_url"] == "https://www.lego.com/product/75379"
    assert summary["product_name"] == "LEGO Star Wars R2-D2 75379"
    assert summary["pillars"]["source"]["source_role"] == "MANUFACTURER"
    assert summary["pillars"]["evidence"]["web_verified_claims"] == 2
    assert summary["pillars"]["identity"]["confidence"] == 0.96
    assert summary["pillars"]["usability"]["passed_checks"] == 6
    assert summary["candidate_summary"][0]["decision"] == "SELECTED"


def test_no_url_summary_is_failed_delivery_and_quantifies_work() -> None:
    result = {
        "job_status": "REVIEW_REQUIRED",
        "coding_ready": False,
        "product": {"row_id": "ROW-2", "main_text": "LEGO R2-D2 75379"},
        "product_identification": _identity(),
        "primary_url": None,
        "url_delivery": {
            "delivered": False,
            "strictly_verified": False,
            "url": None,
            "status": "NO_SAFE_DIRECT_PRODUCT_URL_FOUND_AFTER_BOUNDED_SEARCH",
        },
        "resolution_outcome": {
            "message": "No safe direct product page passed all required gates.",
            "suggested_next_actions": ["Provide a known retailer URL."],
        },
        "primary_url_acceptance": {
            "accepted": False,
            "browser_openable": False,
            "text_scrapable": False,
            "rendered_product_verified": False,
            "exact_product_verified": False,
            "full_feature_coverage": False,
            "durable_url": False,
            "reasons": ["NO_SAFE_DIRECT_PRODUCT_URL_FOUND"],
        },
        "search": {
            "serpapi_requests_used": 3,
            "serpapi_request_limit": 3,
            "stages": [
                {
                    "name": "manufacturer_primary",
                    "results_returned": 12,
                    "new_candidate_urls": 5,
                    "candidates_qualified": 1,
                    "candidates_scraped": 1,
                },
                {
                    "name": "country_alternative",
                    "results_returned": 18,
                    "new_candidate_urls": 6,
                    "candidates_qualified": 2,
                    "candidates_scraped": 2,
                },
                {
                    "name": "global_fallback",
                    "results_returned": 20,
                    "new_candidate_urls": 7,
                    "candidates_qualified": 1,
                    "candidates_scraped": 1,
                },
            ],
        },
        "agentic_browser": {
            "candidate_urls_admitted": 4,
            "candidate_investigations_completed": 3,
        },
        "feature_assessments": [
            {
                "url": "https://example.com/wrong-product",
                "identity_status": "REJECTED",
                "coverage": 0.4,
                "rejection_reasons": ["MODEL_MISMATCH", "URL_NOT_DURABLE"],
            }
        ],
    }

    summary = build_executive_summary(result)

    assert summary["overall_status"] == "URL_DELIVERY_FAILED"
    assert summary["successful_output"] is False
    assert summary["selected_url"] is None
    assert summary["work_completed"] == {
        "search_stages": 3,
        "search_actions_used": 3,
        "search_action_limit": 3,
        "results_seen": 50,
        "candidate_urls_seen": 18,
        "qualified_candidates": 4,
        "pages_extracted": 4,
        "browser_candidates_admitted": 4,
        "browser_investigations_completed": 3,
    }
    assert "not a successful output" in summary["conclusion"]
    assert summary["delivery_failure"]["requires_escalation"] is True
    assert any("model mismatch" in reason.lower() for reason in summary["decision_reasons"])
    assert summary["pillars"]["usability"]["status"] == "DELIVERY_FAILED"


def test_attach_executive_summary_persists_delivery_failure_artifact(tmp_path) -> None:
    result = {
        "job_status": "REVIEW_REQUIRED",
        "coding_ready": False,
        "product": {"row_id": "ROW-3", "main_text": "Unknown product"},
        "artifact_dir": str(tmp_path),
        "product_identification": {"resolution_status": "INSUFFICIENT_EVIDENCE"},
        "primary_url": None,
        "search": {"stages": []},
    }

    attached = attach_executive_summary(result)

    assert attached["executive_summary"]["overall_status"] == "URL_DELIVERY_FAILED"
    assert attached["executive_summary"]["successful_output"] is False
    payload = json.loads((tmp_path / "executive_summary.json").read_text(encoding="utf-8"))
    assert payload == attached["executive_summary"]
