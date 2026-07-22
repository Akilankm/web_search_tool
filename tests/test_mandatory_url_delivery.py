from __future__ import annotations

from product_url_v2.config import RuntimeConfig
from product_url_v2.evaluation import assess_candidate, choose_delivery
from product_url_v2.interpretation import DeterministicProductInterpreter
from product_url_v2.models import (
    CandidateAssessment,
    DeliveryStatus,
    GateStatus,
    IdentityMatch,
    PageEvidence,
    ProductInput,
    SearchResult,
    SourceRole,
)
from product_url_v2.trace import candidate_judgment


def _candidate(index: int, **changes) -> CandidateAssessment:
    url = f"https://shop{index}.example.com/product/item-{index}"
    values = {
        "candidate_id": f"C-{index}",
        "url": url,
        "domain": f"shop{index}.example.com",
        "search_rank": index,
        "search_support": max(0.1, 1.0 - index * 0.05),
        "source_role": SourceRole.GLOBAL_RETAILER,
        "identity_match": IdentityMatch.UNVERIFIED,
        "identity_confidence": 0.0,
        "direct_product_page": GateStatus.FAIL,
        "direct_page_score": 0.15,
        "durable_url": GateStatus.NOT_ASSESSED,
        "country_match": GateStatus.NOT_ASSESSED,
        "retailer_match": GateStatus.NOT_ASSESSED,
        "browser_access": GateStatus.NOT_ASSESSED,
        "text_extractable": GateStatus.FAIL,
        "coding_evidence_complete": GateStatus.FAIL,
        "source_authority": 65,
        "evidence": {
            "search_product_like": True,
            "delivery_basis": "product_like_search_evidence",
            "hard_url_blockers": [],
        },
        "conflicts": (),
        "warnings": ("Identity evidence is incomplete; the URL requires human confirmation.",),
    }
    values.update(changes)
    return CandidateAssessment(**values)


def test_seven_candidates_with_incomplete_evidence_still_deliver_a_url() -> None:
    candidates = tuple(_candidate(index) for index in range(1, 8))

    decision = choose_delivery(candidates)

    assert decision.status is DeliveryStatus.REVIEW_REQUIRED
    assert decision.selected_url == candidates[0].url
    assert decision.selected_candidate_id == candidates[0].candidate_id
    assert decision.selected_url is not None
    assert any("mandatory output" in reason for reason in decision.reasons)


def test_missing_identity_evidence_is_unverified_not_mismatch() -> None:
    product = ProductInput("ROW-1", "MYSTERY ZXQ9999 ITEM", "GB")
    interpretation = DeterministicProductInterpreter().interpret(product)
    url = "https://shop.example.com/product/listing-48271"
    search = SearchResult(url, "Retail product listing", "Available product page", "fixture", "google", "query", 1, True)
    page = PageEvidence(
        requested_url=url,
        final_url=url,
        status_code=403,
        content_type="text/html",
        title="",
        description="",
        visible_text="",
        jsonld_products=(),
        metadata={},
        links=(),
        images=(),
        fetch_status=GateStatus.FAIL,
        fetch_error="HTTP 403",
    )

    candidate = assess_candidate(product, interpretation, search, page, {}, RuntimeConfig())
    decision = choose_delivery((candidate,))

    assert candidate.identity_match is IdentityMatch.UNVERIFIED
    assert candidate.review_eligible is True
    assert candidate.url == url
    assert decision.status is DeliveryStatus.REVIEW_REQUIRED
    assert decision.selected_url == url


def test_non_product_redirect_does_not_replace_original_product_url() -> None:
    product = ProductInput("ROW-2", "ACME ABC123 PRODUCT", "GB")
    interpretation = DeterministicProductInterpreter().interpret(product)
    search_url = "https://shop.example.com/product/acme-abc123"
    search = SearchResult(search_url, "ACME ABC123", "Product page", "fixture", "google", "query", 1, True)
    page = PageEvidence(
        requested_url=search_url,
        final_url="https://shop.example.com/",
        status_code=200,
        content_type="text/html",
        title="Welcome",
        description="",
        visible_text="Welcome to our store",
        jsonld_products=(),
        metadata={},
        links=(),
        images=(),
        fetch_status=GateStatus.PASS,
    )

    candidate = assess_candidate(product, interpretation, search, page, {}, RuntimeConfig())

    assert candidate.url == search_url
    assert candidate.review_eligible is True
    assert any("original product-like search URL was retained" in warning for warning in candidate.warnings)


def test_incomplete_direct_page_verification_is_a_risk_not_a_blocker() -> None:
    candidate = _candidate(1)

    judgment = candidate_judgment(candidate)

    assert candidate.review_eligible is True
    assert any("Direct product-page evidence failed" in risk for risk in judgment["risks"])
    assert not any("Direct product-page evidence failed" in blocker for blocker in judgment["blockers"])


def test_explicit_identifier_conflict_can_still_block_wrong_url() -> None:
    candidate = _candidate(
        1,
        identity_match=IdentityMatch.MISMATCH,
        identity_confidence=0.1,
        conflicts=("EAN/GTIN conflict",),
    )

    decision = choose_delivery((candidate,))

    assert candidate.review_eligible is False
    assert decision.status is DeliveryStatus.FAILED
    assert decision.selected_url is None


def test_transient_url_is_not_delivered() -> None:
    candidate = _candidate(
        1,
        url="https://shop1.example.com/product/item-1?session=abc",
        domain="shop1.example.com",
        durable_url=GateStatus.FAIL,
        evidence={
            "search_product_like": True,
            "delivery_basis": "product_like_search_evidence",
            "hard_url_blockers": ["URL is transient, intermediary or session-bound."],
        },
    )

    decision = choose_delivery((candidate,))

    assert candidate.review_eligible is False
    assert decision.status is DeliveryStatus.FAILED
