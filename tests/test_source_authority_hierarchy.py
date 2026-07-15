from __future__ import annotations

from product_evidence_harness.adaptive_search import BudgetAwareSearchPlanner
from product_evidence_harness.contracts import (
    CandidateScorecard,
    MatchVerification,
    ProductQuery,
    ScrapeResult,
    URLCandidate,
)
from product_evidence_harness.ranker import ProductURLRanker
from product_evidence_harness.source_authority import SourceAuthorityPolicy, SourceTier, source_tier


def product(**overrides) -> ProductQuery:
    values = {
        "row_id": "ROW-1",
        "main_text": "LEGO Star Wars R2-D2 75379",
        "country_code": "GB",
        "retailer_name": None,
        "ean": "5702017584379",
        "language_code": "en",
    }
    values.update(overrides)
    return ProductQuery(**values)


def test_no_retailer_uses_internal_manufacturer_first_hierarchy() -> None:
    policy = SourceAuthorityPolicy()
    assert policy.hierarchy(product()) == (
        "LOCAL_MANUFACTURER",
        "GLOBAL_MANUFACTURER",
        "MAJOR_COUNTRY_RETAILER",
        "OTHER_LOCAL_WEBSITE",
        "OTHER_GLOBAL_WEBSITE",
        "MARKETPLACE_LAST_RESORT",
    )


def test_requested_retailer_overrides_default_hierarchy() -> None:
    policy = SourceAuthorityPolicy()
    requested = product(retailer_name="Amazon UK")
    decision = policy.classify(
        requested,
        URLCandidate(
            url="https://www.amazon.co.uk/dp/B0ABC12345",
            title="LEGO R2-D2 75379",
            domain="amazon.co.uk",
        ),
    )
    assert decision.source_tier in {
        int(SourceTier.REQUESTED_RETAILER_LOCAL),
        int(SourceTier.REQUESTED_RETAILER_GLOBAL),
    }
    assert decision.requested_retailer_match is True


def test_amazon_and_ebay_are_last_resort_when_not_requested() -> None:
    policy = SourceAuthorityPolicy()
    for url in (
        "https://www.amazon.co.uk/dp/B0ABC12345",
        "https://www.ebay.co.uk/itm/123456",
    ):
        decision = policy.classify(product(), URLCandidate(url=url, title="LEGO 75379"))
        assert decision.source_tier == int(SourceTier.MARKETPLACE_LAST_RESORT)
        assert decision.source_role == "MARKETPLACE"


def test_local_and_global_manufacturer_precede_country_retailer() -> None:
    policy = SourceAuthorityPolicy()
    candidates = [
        URLCandidate(
            url="https://www.lego.com/en-gb/product/r2-d2-75379",
            title="Official LEGO R2-D2 75379",
        ),
        URLCandidate(
            url="https://www.lego.com/product/r2-d2-75379",
            title="Official LEGO R2-D2 75379",
        ),
        URLCandidate(
            url="https://toys.example.co.uk/product/lego-75379",
            title="LEGO R2-D2 75379",
            source_types=("engine_google_shopping",),
        ),
    ]
    tagged = policy.tag_candidates(product(), candidates)
    tiers = [source_tier(item) for item in tagged]
    assert tiers[0] == int(SourceTier.LOCAL_MANUFACTURER)
    assert tiers[1] == int(SourceTier.GLOBAL_MANUFACTURER)
    assert tiers[2] == int(SourceTier.MAJOR_COUNTRY_RETAILER)


def test_first_fallback_search_targets_requested_retailer_or_local_manufacturer() -> None:
    planner = BudgetAwareSearchPlanner(require_llm=False)
    manufacturer_action = planner.deterministic_fallback(
        product=product(),
        credit_number=1,
        observations=[],
        handles=[],
        used_signatures=set(),
        available_engines=("google", "google_shopping", "google_ai_mode"),
    )
    assert manufacturer_action.engine == "google"
    assert "SOURCE_TIER:LOCAL_MANUFACTURER" in manufacturer_action.expected_signals
    assert "official manufacturer" in manufacturer_action.query

    retailer_action = planner.deterministic_fallback(
        product=product(retailer_name="Amazon UK"),
        credit_number=1,
        observations=[],
        handles=[],
        used_signatures=set(),
        available_engines=("amazon", "google", "google_shopping"),
    )
    assert retailer_action.engine == "amazon"
    assert "SOURCE_TIER:REQUESTED_RETAILER_LOCAL" in retailer_action.expected_signals


def _scrape(url: str) -> ScrapeResult:
    return ScrapeResult(
        url=url,
        scraped=True,
        success=True,
        reachable=True,
        is_scrapable=True,
        status_code=200,
        final_url=url,
        title="LEGO R2-D2 75379",
        page_product_name="LEGO R2-D2 75379",
        brand="LEGO",
        manufacturer="LEGO",
        looks_like_product_page=True,
        richness_score=0.8,
        word_count=500,
    )


def _verification(url: str) -> MatchVerification:
    return MatchVerification(
        url=url,
        identity_status="VERIFIED",
        ean_check="MATCHED",
        title_check="STRONG",
        quantity_check="UNKNOWN",
        brand_check="MATCHED",
        page_type_check="PRODUCT_DETAIL",
        title_match_score=1.0,
        exact_product_check="EXACT_MATCH",
        variant_check="MATCHED",
    )


def _card(candidate: URLCandidate, confidence: float) -> CandidateScorecard:
    scrape = _scrape(candidate.url)
    verification = _verification(candidate.url)
    return CandidateScorecard(
        candidate=candidate,
        organic_score=1.0,
        ai_score=0.0,
        retailer_score=0.5,
        country_score=1.0,
        ean_score=1.0,
        title_score=1.0,
        product_page_score=1.0,
        scrape_score=1.0,
        identity_score=1.0,
        richness_score=scrape.richness_score,
        weighted_confidence=confidence,
        confidence_cap=1.0,
        final_confidence=confidence,
        validation_status="VERIFIED",
        scrape=scrape,
        verification=verification,
    )


def test_source_authority_is_lexicographic_before_confidence() -> None:
    policy = SourceAuthorityPolicy()
    official, marketplace = policy.tag_candidates(
        product(),
        [
            URLCandidate(url="https://www.lego.com/en-gb/product/r2-d2-75379", title="Official LEGO product"),
            URLCandidate(url="https://www.amazon.co.uk/dp/B0ABC12345", title="LEGO product"),
        ],
    )
    ranker = ProductURLRanker()
    official_key = ranker._sort_key(_card(official, 0.82))
    marketplace_key = ranker._sort_key(_card(marketplace, 0.99))
    assert official_key > marketplace_key
