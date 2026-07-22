from __future__ import annotations

import json
from pathlib import Path

from product_evidence_harness import mandatory_url_policy
from product_evidence_harness.executive_summary import build_executive_summary
from product_evidence_harness.structured_no_url_outcome import is_structured_no_url_outcome
from product_evidence_harness.url_delivery_recovery import (
    collect_delivery_candidates,
    direct_external_product_url,
    select_best_delivery_candidate,
)


def _base_result(tmp_path: Path) -> dict:
    return {
        "job_status": "REVIEW_REQUIRED",
        "artifact_dir": str(tmp_path),
        "product": {
            "row_id": "ROW-URL",
            "main_text": "Exact Example Product 123",
            "country_code": "GB",
        },
        "product_identification": {
            "resolution_status": "PROBABLE",
            "leading_hypothesis": {
                "canonical_name": "Exact Example Product 123",
                "posterior_probability": 0.88,
            },
        },
        "search": {
            "market_decision_path": [
                "manufacturer_primary",
                "country_alternative",
                "global_fallback",
            ],
            "serpapi_requests_used": 3,
            "serpapi_request_limit": 3,
            "stages": [],
        },
        "product_match": {},
        "primary_url": None,
        "primary_url_role": "NONE",
        "manufacturer_url": None,
        "retailer_url": None,
        "primary_url_acceptance": {"accepted": False},
        "source_selection": {"source_role": "NONE"},
        "evidence_set": {},
        "feature_assessments": [],
        "browser_evidence": [],
        "candidate_investigations": [],
        "business_judgement_review": {"steps": []},
        "coding_ready": False,
    }


def test_direct_url_filter_blocks_intermediaries_and_category_pages() -> None:
    assert direct_external_product_url("https://www.google.com/search?q=product") is None
    assert direct_external_product_url("https://shop.example.com/category/toys") is None
    assert direct_external_product_url("https://shop.example.com/product/exact-123") == (
        "https://shop.example.com/product/exact-123"
    )


def test_candidate_records_rescue_best_review_url(tmp_path: Path) -> None:
    result = _base_result(tmp_path)
    result["candidate_records"] = [
        {
            "url": "https://shop.example.com/search?q=exact",
            "identity_status": "UNVERIFIED",
            "final_status": "SERP_REJECTED_URL_TYPE",
        },
        {
            "url": "https://retailer.example.com/product/exact-example-product-123",
            "identity_status": "PROBABLE",
            "source_role": "REQUESTED_RETAILER",
            "product_page_likelihood": 0.92,
            "browser_openable": True,
            "content_extracted": True,
            "confidence": 0.81,
            "coverage": 0.75,
            "final_status": "ELIGIBLE_NOT_SELECTED",
        },
    ]

    delivered = mandatory_url_policy._enforce_orchestrated_delivery(result)

    expected = "https://retailer.example.com/product/exact-example-product-123"
    assert delivered["primary_url"] == expected
    assert delivered["url_delivery"]["delivered"] is True
    assert delivered["url_delivery"]["status"] == "BEST_AVAILABLE_REVIEW_URL"
    assert delivered["url_delivery_recovery"]["selected"]["origin"] == (
        "result:candidate_records"
    )
    assert delivered["job_status"] == "REVIEW_REQUIRED"


def test_confirmed_mismatch_is_never_promoted(tmp_path: Path) -> None:
    result = _base_result(tmp_path)
    result["candidate_records"] = [
        {
            "url": "https://retailer.example.com/product/wrong-variant",
            "identity_status": "MISMATCH",
            "confidence": 0.99,
            "product_page_likelihood": 1.0,
        },
        {
            "url": "https://manufacturer.example.com/products/exact-example-product-123",
            "identity_status": "UNVERIFIED",
            "source_role": "MANUFACTURER",
            "product_page_likelihood": 0.72,
            "confidence": 0.55,
        },
    ]

    best = select_best_delivery_candidate(result)
    assert best is not None
    assert best.url == "https://manufacturer.example.com/products/exact-example-product-123"
    assert "wrong-variant" not in {item.url for item in collect_delivery_candidates(result)}


def test_candidate_state_artifact_is_used_when_result_fields_are_empty(tmp_path: Path) -> None:
    result = _base_result(tmp_path)
    (tmp_path / "candidate_state.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "url": "https://shop.example.com/product/exact-example-product-123",
                        "title": "Exact Example Product 123",
                        "best_position": 1,
                    }
                ],
                "candidate_admissions": [
                    {
                        "canonical_url": "https://shop.example.com/product/exact-example-product-123",
                        "admitted_for_scrape": True,
                        "preflight_score": 0.74,
                    }
                ],
                "scrapes": {
                    "https://shop.example.com/product/exact-example-product-123": {
                        "success": True,
                        "reachable": True,
                        "looks_like_product_page": True,
                        "is_scrapable": True,
                    }
                },
                "verifications": {
                    "https://shop.example.com/product/exact-example-product-123": {
                        "identity_status": "PROBABLE"
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    delivered = mandatory_url_policy._enforce_orchestrated_delivery(result)
    assert delivered["primary_url"] == (
        "https://shop.example.com/product/exact-example-product-123"
    )
    assert delivered["url_delivery_recovery"]["selected"]["origin"] == (
        "artifact:candidate_state"
    )


def test_zero_direct_candidates_remains_exceptional_escalation(tmp_path: Path) -> None:
    result = _base_result(tmp_path)
    result["candidate_records"] = [
        {
            "url": "https://shop.example.com/category/toys",
            "identity_status": "UNVERIFIED",
        },
        {
            "url": "https://shop.example.com/product/wrong-product",
            "identity_status": "MISMATCH",
        },
    ]

    outcome = mandatory_url_policy._enforce_orchestrated_delivery(result)
    assert is_structured_no_url_outcome(outcome)
    summary = build_executive_summary(outcome)
    assert summary["overall_status"] == "URL_DELIVERY_FAILED"
    assert summary["successful_output"] is False
    assert summary["delivery_failure"]["requires_escalation"] is True
    assert "not a successful output" in summary["conclusion"]


def test_review_url_is_a_successful_delivery_output(tmp_path: Path) -> None:
    result = _base_result(tmp_path)
    result.update(
        {
            "primary_url": "https://shop.example.com/product/exact-example-product-123",
            "primary_url_role": "RETAILER",
            "url_delivery": {
                "required": True,
                "delivered": True,
                "url": "https://shop.example.com/product/exact-example-product-123",
                "strictly_verified": False,
                "status": "BEST_AVAILABLE_REVIEW_URL",
            },
        }
    )
    summary = build_executive_summary(result)
    assert summary["overall_status"] == "URL_DELIVERED_REVIEW_REQUIRED"
    assert summary["successful_output"] is True
    assert summary["selected_url"] == result["primary_url"]
