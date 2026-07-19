from __future__ import annotations

from product_evidence_harness.contracts import (
    CandidateScorecard,
    MatchVerification,
    ProductQuery,
    ScrapeResult,
    URLCandidate,
)
from product_evidence_harness.ranker import ProductURLRanker
from product_evidence_harness.source_authority import SourceAuthorityPolicy, SourceTier


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


def test_business_hierarchy_is_manufacturer_first() -> None:
    policy = SourceAuthorityPolicy()
    assert policy.hierarchy(product())[:3] == (
        "LOCAL_MANUFACTURER",
        "GLOBAL_MANUFACTURER",
        "MAJOR_COUNTRY_RETAILER",
    )
    assert policy.hierarchy(product(retailer_name="Amazon UK"))[:5] == (
        "LOCAL_MANUFACTURER",
        "GLOBAL_MANUFACTURER",
        "REQUESTED_RETAILER_LOCAL",
        "REQUESTED_RETAILER_GLOBAL",
        "MAJOR_COUNTRY_RETAILER",
    )


def test_requested_retailer_classification_remains_available() -> None:
    decision = SourceAuthorityPolicy().classify(
        product(retailer_name="Amazon UK"),
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


def test_manufacturer_classification_precedes_retailer_override() -> None:
    decision = SourceAuthorityPolicy().classify(
        product(retailer_name="LEGO"),
        URLCandidate(
            url="https://www.lego.com/en-gb/product/r2-d2-75379",
            title="Official LEGO R2-D2 75379",
            domain="lego.com",
        ),
        _scrape("https://www.lego.com/en-gb/product/r2-d2-75379"),
    )
    assert decision.source_tier in {
        int(SourceTier.LOCAL_MANUFACTURER),
        int(SourceTier.GLOBAL_MANUFACTURER),
    }
    assert decision.source_role == "MANUFACTURER"
    assert decision.manufacturer_match is True


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


def _card(
    task: ProductQuery,
    url: str,
    *,
    country_check: str,
    retailer_check: str = "NOT_PROVIDED",
    confidence: float = 0.9,
    source_types: tuple[str, ...] = (),
) -> CandidateScorecard:
    scrape = _scrape(url)
    candidate = URLCandidate(
        url=url,
        title="LEGO R2-D2 75379",
        source_types=source_types,
    )
    candidate = SourceAuthorityPolicy().tag_candidates(
        task,
        [candidate],
        {url: scrape},
    )[0]
    return CandidateScorecard(
        candidate=candidate,
        organic_score=1.0,
        ai_score=0.0,
        retailer_score=1.0 if retailer_check == "MATCHED" else 0.0,
        country_score=1.0 if country_check == "MATCHED" else 0.0,
        ean_score=1.0,
        title_score=1.0,
        product_page_score=1.0,
        scrape_score=1.0,
        identity_score=1.0,
        richness_score=0.8,
        weighted_confidence=confidence,
        confidence_cap=1.0,
        final_confidence=confidence,
        validation_status="VERIFIED",
        scrape=scrape,
        verification=_verification(url),
        retailer_check=retailer_check,
        country_check=country_check,
    )


def test_manufacturer_authority_beats_requested_retailer_after_identity_gates() -> None:
    task = product(retailer_name="Amazon UK")
    manufacturer = _card(
        task,
        "https://www.lego.com/en-gb/product/r2-d2-75379",
        country_check="MATCHED",
        confidence=0.82,
    )
    requested = _card(
        task,
        "https://www.amazon.co.uk/dp/B0ABC12345",
        country_check="MATCHED",
        retailer_check="MATCHED",
        confidence=0.99,
        source_types=("engine_amazon",),
    )

    ranker = ProductURLRanker()
    assert ranker._sort_key(manufacturer) > ranker._sort_key(requested)
