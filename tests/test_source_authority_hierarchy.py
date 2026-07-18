from __future__ import annotations

from product_evidence_harness.adaptive_search import BudgetAwareSearchPlanner
from product_evidence_harness.contracts import CandidateScorecard, MatchVerification, ProductQuery, ScrapeResult, URLCandidate
from product_evidence_harness.ranker import ProductURLRanker
from product_evidence_harness.source_authority import SourceAuthorityPolicy, SourceTier


def product(**overrides) -> ProductQuery:
    values = {"row_id": "ROW-1", "main_text": "LEGO Star Wars R2-D2 75379", "country_code": "GB", "retailer_name": None, "ean": "5702017584379", "language_code": "en"}
    values.update(overrides)
    return ProductQuery(**values)


def test_business_hierarchy_is_market_first() -> None:
    policy = SourceAuthorityPolicy()
    assert policy.hierarchy(product()) == ("COUNTRY_ALTERNATIVE", "GLOBAL_FALLBACK")
    assert policy.hierarchy(product(retailer_name="Amazon UK")) == ("REQUESTED_RETAILER", "COUNTRY_ALTERNATIVE", "GLOBAL_FALLBACK")


def test_requested_retailer_classification_remains_available() -> None:
    decision = SourceAuthorityPolicy().classify(
        product(retailer_name="Amazon UK"),
        URLCandidate(url="https://www.amazon.co.uk/dp/B0ABC12345", title="LEGO R2-D2 75379", domain="amazon.co.uk"),
    )
    assert decision.source_tier in {int(SourceTier.REQUESTED_RETAILER_LOCAL), int(SourceTier.REQUESTED_RETAILER_GLOBAL)}
    assert decision.requested_retailer_match is True


def test_planner_actions_follow_requested_country_global_route() -> None:
    planner = BudgetAwareSearchPlanner(require_llm=False)
    requested = product(retailer_name="Amazon UK")
    first = planner.deterministic_fallback(product=requested, credit_number=1, observations=[], handles=[], used_signatures=set(), available_engines=("amazon", "google", "google_shopping"))
    second = planner.deterministic_fallback(product=requested, credit_number=2, observations=[], handles=[], used_signatures={first.signature()}, available_engines=("amazon", "google", "google_shopping", "google_ai_mode"))
    third = planner.deterministic_fallback(product=requested, credit_number=3, observations=[], handles=[], used_signatures={first.signature(), second.signature()}, available_engines=("google", "google_shopping", "google_ai_mode"))
    assert first.scope == "country" and "requested_retailer" in first.expected_signals and "Amazon UK" in first.query
    assert second.scope == "country" and "country_alternative" in second.expected_signals and '"Amazon UK"' not in second.query
    assert third.scope == "global" and "global_fallback" in third.expected_signals


def _scrape(url: str) -> ScrapeResult:
    return ScrapeResult(url=url, scraped=True, success=True, reachable=True, is_scrapable=True, status_code=200, final_url=url, title="LEGO R2-D2 75379", page_product_name="LEGO R2-D2 75379", brand="LEGO", manufacturer="LEGO", looks_like_product_page=True, richness_score=0.8, word_count=500)


def _verification(url: str) -> MatchVerification:
    return MatchVerification(url=url, identity_status="VERIFIED", ean_check="MATCHED", title_check="STRONG", quantity_check="UNKNOWN", brand_check="MATCHED", page_type_check="PRODUCT_DETAIL", title_match_score=1.0, exact_product_check="EXACT_MATCH", variant_check="MATCHED")


def _card(url: str, *, country_check: str, retailer_check: str = "NOT_PROVIDED", confidence: float = 0.9) -> CandidateScorecard:
    scrape = _scrape(url)
    return CandidateScorecard(candidate=URLCandidate(url=url, title="LEGO R2-D2 75379"), organic_score=1.0, ai_score=0.0, retailer_score=1.0 if retailer_check == "MATCHED" else 0.0, country_score=1.0 if country_check == "MATCHED" else 0.0, ean_score=1.0, title_score=1.0, product_page_score=1.0, scrape_score=1.0, identity_score=1.0, richness_score=0.8, weighted_confidence=confidence, confidence_cap=1.0, final_confidence=confidence, validation_status="VERIFIED", scrape=scrape, verification=_verification(url), retailer_check=retailer_check, country_check=country_check)


def test_market_precedence_beats_global_source_branding() -> None:
    ranker = ProductURLRanker()
    requested = _card("https://requested.example.co.uk/product/75379", country_check="MATCHED", retailer_check="MATCHED", confidence=0.82)
    country = _card("https://country.example.co.uk/product/75379", country_check="MATCHED", confidence=0.90)
    global_page = _card("https://www.lego.com/product/75379", country_check="ALTERNATIVE", confidence=0.99)
    assert ranker._sort_key(requested) > ranker._sort_key(country)
    assert ranker._sort_key(country) > ranker._sort_key(global_page)
