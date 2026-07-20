from __future__ import annotations

from product_evidence_harness import mandatory_url_policy
from product_evidence_harness.adaptive_search import SearchEngine, SearchHandle
from product_evidence_harness.config import HarnessPolicy
from product_evidence_harness.contracts import (
    CandidateScorecard,
    ProductQuery,
    SearchBudgetSnapshot,
    URLCandidate,
)
from product_evidence_harness.mandatory_url_policy import (
    _direct_external_url,
    _mandatory_recovery_action,
)
from product_evidence_harness.selector import FinalSelector
from product_evidence_harness.structured_no_url_outcome import (
    NO_URL_DELIVERY_STATUS,
    NO_URL_OUTCOME_CODE,
    is_structured_no_url_outcome,
)


def _card(url: str, *, hard_failures: tuple[str, ...] = ()) -> CandidateScorecard:
    return CandidateScorecard(
        candidate=URLCandidate(
            url=url,
            title="Exact Example Product 123",
            source_types=("engine_google", "source_tier_4"),
            best_position=1,
        ),
        organic_score=0.8,
        ai_score=0.0,
        retailer_score=0.0,
        country_score=0.8,
        ean_score=0.0,
        title_score=0.8,
        product_page_score=0.8,
        scrape_score=0.0,
        identity_score=0.5,
        richness_score=0.2,
        weighted_confidence=0.6,
        confidence_cap=1.0,
        final_confidence=0.6,
        validation_status="REJECTED" if hard_failures else "NEEDS_REVIEW",
        hard_failures=hard_failures,
    )


def test_direct_url_contract_rejects_intermediaries_and_non_product_pages() -> None:
    assert _direct_external_url("https://www.google.com/search?q=product") is None
    assert _direct_external_url("https://shop.example.com/search?q=product") is None
    assert _direct_external_url("https://shop.example.com/category/toys") is None
    assert (
        _direct_external_url("https://shop.example.com/product/exact-example-product-123")
        == "https://shop.example.com/product/exact-example-product-123"
    )


def test_selector_returns_real_best_available_url_even_when_strictly_rejected() -> None:
    selector = FinalSelector(
        HarnessPolicy(return_rejected_reference_as_product_url=False)
    )
    match = selector.select(
        task=ProductQuery(
            row_id="ROW-1",
            main_text="Exact Example Product 123",
            country_code="GB",
        ),
        scorecards=[
            _card(
                "https://shop.example.com/product/exact-example-product-123",
                hard_failures=("IDENTITY_NOT_FULLY_VERIFIED",),
            )
        ],
        termination_reason="ADAPTIVE_SEARCH_CREDIT_BUDGET_EXHAUSTED",
        budget_snapshot=SearchBudgetSnapshot(
            organic_used=3,
            ai_mode_used=0,
            scrape_used=1,
            max_organic=3,
            max_ai_mode=0,
            max_scrapes=6,
        ),
    )

    assert match.product_url == "https://shop.example.com/product/exact-example-product-123"
    assert match.best_available_url == match.product_url
    assert match.url_decision_status == "MANDATORY_BEST_AVAILABLE_PRODUCT_URL"
    assert match.needs_review is True


def test_review_result_preserves_product_url_in_all_primary_output_fields(tmp_path) -> None:
    result = {
        "job_status": "REVIEW_REQUIRED",
        "artifact_dir": str(tmp_path),
        "primary_url": None,
        "product_match": {
            "product_url": None,
            "best_available_url": "https://shop.example.com/product/exact-example-product-123",
            "best_reference_url": None,
        },
        "primary_url_acceptance": {
            "accepted": False,
            "primary_url": None,
            "reasons": ["PRIMARY_URL_MISSING_REQUESTED_FEATURES"],
        },
        "evidence_set": {
            "primary_url": None,
            "selected_urls": [
                "https://shop.example.com/product/exact-example-product-123"
            ],
            "supplementary_urls": [],
        },
        "feature_assessments": [],
        "browser_evidence": [],
    }

    delivered = mandatory_url_policy._enforce_orchestrated_delivery(result)

    expected = "https://shop.example.com/product/exact-example-product-123"
    assert delivered["primary_url"] == expected
    assert delivered["product_match"]["product_url"] == expected
    assert delivered["evidence_set"]["primary_url"] == expected
    assert delivered["primary_url_acceptance"]["accepted"] is False
    assert delivered["url_delivery"] == {
        "required": True,
        "delivered": True,
        "url": expected,
        "strictly_verified": False,
        "status": "BEST_AVAILABLE_REVIEW_URL",
        "empty_url_is_success": False,
    }
    assert (tmp_path / "mandatory_url_delivery.json").is_file()


def test_empty_url_is_a_structured_review_outcome_with_audit_artifact(tmp_path) -> None:
    result = mandatory_url_policy._enforce_orchestrated_delivery(
        {
            "job_status": "REVIEW_REQUIRED",
            "artifact_dir": str(tmp_path),
            "product": {
                "row_id": "ROW-NO-URL",
                "main_text": "Obscure exact product",
                "country_code": "GB",
            },
            "search": {
                "serpapi_requests_used": 3,
                "serpapi_request_limit": 3,
                "stages": [
                    {"name": "manufacturer_primary", "results_returned": 0},
                    {"name": "country_alternative", "results_returned": 0},
                    {"name": "global_fallback", "results_returned": 0},
                ],
            },
            "product_match": {},
            "primary_url_acceptance": {"accepted": False},
            "evidence_set": {},
            "feature_assessments": [],
            "browser_evidence": [],
            "candidate_investigations": [],
        }
    )

    assert is_structured_no_url_outcome(result)
    assert result["job_status"] == "REVIEW_REQUIRED"
    assert result["coding_ready"] is False
    assert result["primary_url"] is None
    assert result["primary_url_role"] == "NONE"
    assert result["url_delivery"]["delivered"] is False
    assert result["url_delivery"]["status"] == NO_URL_DELIVERY_STATUS
    assert result["resolution_outcome"]["code"] == NO_URL_OUTCOME_CODE
    assert result["resolution_outcome"]["serpapi_requests_used"] == 3
    assert result["resolution_outcome"]["url_fabricated"] is False
    assert (tmp_path / "no_url_resolution.json").is_file()
    assert (tmp_path / "orchestrated_result.json").is_file()


def test_final_credit_prefers_real_immersive_product_token() -> None:
    product = ProductQuery(
        row_id="ROW-2",
        main_text="Exact Example Product 123",
        country_code="GB",
    )
    action = _mandatory_recovery_action(
        None,
        product=product,
        handles=[
            SearchHandle(
                kind="immersive_product_page_token",
                value="real-token",
                source_engine=SearchEngine.GOOGLE_SHOPPING.value,
            )
        ],
        available_engines=[
            SearchEngine.GOOGLE.value,
            SearchEngine.GOOGLE_IMMERSIVE_PRODUCT.value,
        ],
    )

    assert action.engine == SearchEngine.GOOGLE_IMMERSIVE_PRODUCT.value
    assert action.page_token == "real-token"
    assert action.planner_source == "mandatory_recovery"
