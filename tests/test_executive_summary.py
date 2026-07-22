from __future__ import annotations

import json

from src.product_evidence_harness.url_delivery_summary import (
    attach_url_delivery_summary,
    build_url_delivery_summary,
)


def _identity() -> dict:
    return {
        "resolution_status": "EXACT",
        "leading_hypothesis": {
            "canonical_name": "LEGO Star Wars R2-D2 75379",
            "posterior_probability": 0.96,
        },
        "hypotheses": [{"canonical_name": "LEGO Star Wars R2-D2 75379"}],
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


def _verified_result() -> dict:
    url = "https://www.lego.com/product/75379"
    return {
        "job_status": "COMPLETED",
        "coding_ready": True,
        "product": {"row_id": "ROW-1", "main_text": "LEGO R2-D2 75379"},
        "product_identification": _identity(),
        "primary_url": url,
        "manufacturer_url": url,
        "retailer_url": None,
        "url_delivery": {
            "delivered": True,
            "strictly_verified": True,
            "url": url,
        },
        "source_selection": {
            "source_role": "MANUFACTURER",
            "source_tier_name": "GLOBAL_MANUFACTURER",
        },
        "primary_url_acceptance": {
            "accepted": True,
            "browser_openable": True,
            "text_scrapable": True,
            "rendered_product_verified": True,
            "exact_product_verified": True,
            "full_feature_coverage": True,
            "durable_url": True,
        },
        "evidence_set": {"required_coverage": 1.0},
        "search": {"serpapi_requests_used": 2, "serpapi_request_limit": 3, "stages": []},
        "feature_assessments": [
            {
                "url": url,
                "identity_status": "VERIFIED",
                "coverage": 1.0,
                "source_role": "MANUFACTURER",
            }
        ],
    }


def test_verified_url_summary_is_successful_delivery() -> None:
    summary = build_url_delivery_summary(_verified_result())
    assert summary["overall_status"] == "URL_DELIVERED_VERIFIED"
    assert summary["successful_output"] is True
    assert summary["selected_url"] == "https://www.lego.com/product/75379"
    assert summary["pillars"]["source"]["status"] == "DELIVERED_VERIFIED"
    assert summary["pillars"]["usability"]["status"] == "READY"


def test_review_url_summary_remains_successful_delivery() -> None:
    result = _verified_result()
    result["job_status"] = "REVIEW_REQUIRED"
    result["coding_ready"] = False
    result["url_delivery"]["strictly_verified"] = False
    result["primary_url_acceptance"]["accepted"] = False
    result["primary_url_acceptance"]["full_feature_coverage"] = False

    summary = build_url_delivery_summary(result)
    assert summary["overall_status"] == "URL_DELIVERED_REVIEW_REQUIRED"
    assert summary["successful_output"] is True
    assert "strongest real direct product URL was delivered" in summary["conclusion"]


def test_empty_url_summary_is_exceptional_failed_delivery() -> None:
    result = {
        "job_status": "REVIEW_REQUIRED",
        "coding_ready": False,
        "product": {"row_id": "ROW-2", "main_text": "Unknown product"},
        "product_identification": {"resolution_status": "INSUFFICIENT_EVIDENCE"},
        "primary_url": None,
        "url_delivery": {
            "delivered": False,
            "status": "NO_SAFE_DIRECT_PRODUCT_URL_FOUND_AFTER_BOUNDED_SEARCH",
        },
        "search": {
            "serpapi_requests_used": 3,
            "serpapi_request_limit": 3,
            "stages": [{"results_returned": 20, "new_candidate_urls": 5}],
        },
    }
    summary = build_url_delivery_summary(result)
    assert summary["overall_status"] == "URL_DELIVERY_FAILED"
    assert summary["successful_output"] is False
    assert summary["delivery_failure"]["requires_escalation"] is True
    assert "not a successful output" in summary["conclusion"]


def test_attach_url_delivery_summary_persists_artifact(tmp_path) -> None:
    result = _verified_result()
    result["artifact_dir"] = str(tmp_path)
    attached = attach_url_delivery_summary(result)
    payload = json.loads((tmp_path / "executive_summary.json").read_text(encoding="utf-8"))
    assert payload == attached["executive_summary"]
    assert payload["overall_status"] == "URL_DELIVERED_VERIFIED"
