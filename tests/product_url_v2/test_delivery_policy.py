from __future__ import annotations

from product_url_v2 import (
    BudgetPolicy,
    CandidateAllocationPolicy,
    CandidateAssessment,
    DeliveryStatus,
    GateStatus,
    IdentityMatch,
    MandatoryURLDeliveryPolicy,
    ProductInput,
    SourceRole,
    build_search_objectives,
    is_structurally_product_like_url,
)


def _candidate(
    candidate_id: str,
    url: str,
    *,
    source_role: SourceRole = SourceRole.COUNTRY_RETAILER,
    hypothesis_id: str = "H1",
    identity_match: IdentityMatch = IdentityMatch.EXACT,
    identity_confidence: float = 0.95,
    browser_access: GateStatus = GateStatus.PASS,
    text_extractable: GateStatus = GateStatus.PASS,
    direct_product_page: GateStatus = GateStatus.PASS,
    durable_url: GateStatus = GateStatus.PASS,
    coding_evidence_complete: GateStatus = GateStatus.PASS,
    source_authority: int = 70,
    hard_conflicts: tuple[str, ...] = (),
) -> CandidateAssessment:
    from urllib.parse import urlparse

    return CandidateAssessment(
        candidate_id=candidate_id,
        url=url,
        domain=urlparse(url).hostname or "",
        source_role=source_role,
        hypothesis_id=hypothesis_id,
        search_rank=1,
        search_support=0.90,
        identity_match=identity_match,
        identity_confidence=identity_confidence,
        browser_access=browser_access,
        text_extractable=text_extractable,
        direct_product_page=direct_product_page,
        durable_url=durable_url,
        country_match=GateStatus.PASS,
        retailer_match=GateStatus.NOT_ASSESSED,
        coding_evidence_complete=coding_evidence_complete,
        source_authority=source_authority,
        hard_conflicts=hard_conflicts,
    )


def test_missing_coding_evidence_retains_real_product_url_for_review() -> None:
    candidate = _candidate(
        "C1",
        "https://www.toytans.ch/de/pokemon-booster/2692-pokemon-me04-wachsendes-chaos-booster-pack-de-196214141070.html",
        coding_evidence_complete=GateStatus.FAIL,
    )

    decision = MandatoryURLDeliveryPolicy().select([candidate])

    assert decision.status is DeliveryStatus.REVIEW_REQUIRED
    assert decision.selected_url == candidate.url
    assert decision.strictly_verified is False
    assert decision.coding_ready is False
    assert any("coding fact" in reason for reason in decision.reasons)


def test_not_assessed_browser_state_is_not_fabricated_as_failure() -> None:
    candidate = _candidate(
        "C1",
        "https://retailer.example/product/exact-item",
        browser_access=GateStatus.NOT_ASSESSED,
        text_extractable=GateStatus.NOT_ASSESSED,
        coding_evidence_complete=GateStatus.NOT_ASSESSED,
    )

    assert candidate.browser_access is GateStatus.NOT_ASSESSED
    assert candidate.browser_assessed is False

    decision = MandatoryURLDeliveryPolicy().select([candidate])

    assert decision.status is DeliveryStatus.REVIEW_REQUIRED
    assert decision.selected_url == candidate.url
    assert any("not assessed" in reason.lower() for reason in decision.reasons)


def test_browser_automation_failure_does_not_claim_human_url_failure() -> None:
    candidate = _candidate(
        "C1",
        "https://retailer.example/product/exact-item",
        browser_access=GateStatus.FAIL,
        text_extractable=GateStatus.FAIL,
        coding_evidence_complete=GateStatus.NOT_ASSESSED,
    )

    decision = MandatoryURLDeliveryPolicy().select([candidate])

    assert decision.status is DeliveryStatus.REVIEW_REQUIRED
    assert decision.selected_url == candidate.url
    assert any("human cannot open" in reason for reason in decision.reasons)


def test_explicit_wrong_product_is_never_delivered() -> None:
    candidate = _candidate(
        "C1",
        "https://retailer.example/product/wrong-item",
        identity_match=IdentityMatch.MISMATCH,
        identity_confidence=0.99,
        hard_conflicts=("wrong pack configuration",),
    )

    decision = MandatoryURLDeliveryPolicy().select([candidate])

    assert decision.status is DeliveryStatus.FAILED
    assert decision.selected_url is None


def test_homepage_category_search_and_media_urls_are_never_delivered() -> None:
    blocked = (
        "https://www.kaufland.at/",
        "https://shop.example/category/pokemon",
        "https://shop.example/search?q=wachsendes+chaos",
        "https://shop.example/assets/product.pdf",
        "https://www.google.com/search?q=product",
    )

    assert all(not is_structurally_product_like_url(url) for url in blocked)

    candidates = [
        _candidate(f"C{index}", url, direct_product_page=GateStatus.NOT_ASSESSED)
        for index, url in enumerate(blocked, start=1)
    ]
    decision = MandatoryURLDeliveryPolicy().select(candidates)

    assert decision.status is DeliveryStatus.FAILED
    assert decision.selected_url is None


def test_product_slug_under_collection_remains_eligible() -> None:
    url = "https://zadoys.ch/en/products/pokemon-mega-series-wachsendes-chaos-me04-booster-bundle-de"

    assert is_structurally_product_like_url(url) is True


def test_strict_candidate_is_verified_and_coding_ready() -> None:
    candidate = _candidate(
        "C1",
        "https://manufacturer.example/products/exact-item",
        source_role=SourceRole.LOCAL_MANUFACTURER,
        source_authority=100,
    )

    decision = MandatoryURLDeliveryPolicy().select([candidate])

    assert decision.status is DeliveryStatus.VERIFIED
    assert decision.selected_url == candidate.url
    assert decision.strictly_verified is True
    assert decision.coding_ready is True


def test_browser_budget_covers_manufacturer_retailer_and_competing_hypothesis() -> None:
    candidates = [
        _candidate(
            "M1",
            "https://manufacturer.example/products/item",
            source_role=SourceRole.GLOBAL_MANUFACTURER,
            source_authority=95,
        ).with_updates(browser_access=GateStatus.NOT_ASSESSED),
        _candidate(
            "R1",
            "https://requested.example/product/item",
            source_role=SourceRole.REQUESTED_RETAILER,
            source_authority=80,
        ).with_updates(browser_access=GateStatus.NOT_ASSESSED),
        _candidate(
            "A1",
            "https://alternative.example/product/item-bundle",
            source_role=SourceRole.COUNTRY_RETAILER,
            hypothesis_id="H2",
            identity_match=IdentityMatch.PROBABLE,
            identity_confidence=0.80,
            source_authority=65,
        ).with_updates(browser_access=GateStatus.NOT_ASSESSED),
        _candidate(
            "D1",
            "https://duplicate.example/product/item",
            source_role=SourceRole.GLOBAL_RETAILER,
            source_authority=60,
        ).with_updates(browser_access=GateStatus.NOT_ASSESSED),
    ]

    selected = CandidateAllocationPolicy(
        BudgetPolicy(max_browser_investigations=3)
    ).select_for_browser(candidates)

    assert {item.candidate_id for item in selected} == {"M1", "R1", "A1"}


def test_search_objectives_preserve_identity_then_uncertainty_then_recovery() -> None:
    objectives = build_search_objectives(
        ProductInput(
            row_id="ROW-1",
            main_text="PKM ME04 WACHSENDES CHAOS BOOSTER",
            country_code="CH",
            retailer_name=None,
            ean="196214141070",
            language_code="de",
        )
    )

    assert [item.sequence for item in objectives] == [1, 2, 3]
    assert objectives[0].purpose == "resolve_exact_identifier"
    assert objectives[1].purpose == "resolve_highest_identity_uncertainty"
    assert objectives[2].purpose == "mandatory_direct_url_recovery"
