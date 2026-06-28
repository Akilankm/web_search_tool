from __future__ import annotations

from product_evidence_harness import ProductQuery
from product_evidence_harness.config import HarnessConfig, HarnessPolicy
from product_evidence_harness.contracts import MatchVerification, ScrapeResult, URLCandidate
from product_evidence_harness.country_profiles import CountryProfileRegistry
from product_evidence_harness.query_builder import QueryBuilder
from product_evidence_harness.ranker import ProductURLRanker
from product_evidence_harness.selector import FinalSelector
from product_evidence_harness.budget import BudgetTracker


def _verified(url: str) -> tuple[ScrapeResult, MatchVerification]:
    scrape = ScrapeResult(
        url=url,
        scraped=True,
        success=True,
        reachable=True,
        is_scrapable=True,
        status_code=200,
        final_url=url,
        richness_score=0.6,
        looks_like_product_page=True,
    )
    verification = MatchVerification(
        url=url,
        identity_status="VERIFIED",
        ean_check="MATCHED",
        title_check="STRONG",
        quantity_check="MATCHED",
        brand_check="MATCHED",
        page_type_check="PRODUCT_DETAIL",
        title_match_score=1.0,
    )
    return scrape, verification


def test_ch_profile_handles_multiple_languages_and_country_domains():
    registry = CountryProfileRegistry.load()
    profile = registry.get("CH")
    assert profile.languages[:4] == ("de", "fr", "it", "rm")
    assert registry.domain_matches_country("https://www.any-retailer.ch/de/s5/product/x", "CH")
    assert registry.domain_matches_country("https://example.swiss/product/x", "CH")
    assert not registry.domain_matches_country("https://example.de/product/x", "CH")


def test_query_builder_boosts_ean_and_country_scope_for_ch():
    qb = QueryBuilder(country_profiles=CountryProfileRegistry.load())
    q = qb.primary(ProductQuery(main_text="Lego City Feuerwehr", country_code="CH", ean="5702011234567"))
    assert q.index("5702011234567") < q.index('"Lego City Feuerwehr"')
    assert "site:.ch" in q or "site:.swiss" in q
    assert any(term in q for term in ["kaufen", "acheter", "comprare"])


def test_selector_prefers_reviewable_country_candidate_before_verified_global():
    task = ProductQuery(main_text="Acme Widget 18 ks", country_code="CH", ean="4002051612345")
    policy = HarnessPolicy(require_country_specific_before_global=True, allow_global_fallback=True, min_review_confidence=0.20)
    ranker = ProductURLRanker(policy=policy, country_profiles=CountryProfileRegistry.load())
    selector = FinalSelector(policy=policy)

    country_url = "https://www.any-retailer.ch/de/s5/product/acme-widget-18-ks"
    global_url = "https://www.example.com/product/acme-widget-18-ks"
    country_scrape, country_verification = _verified(country_url)
    global_scrape, global_verification = _verified(global_url)

    # Make country card needs-review by lowering confidence after score via high threshold,
    # but keep it usable and scrapable. Global is also verified, but should not preempt
    # country evidence due to country-first policy.
    candidates = [
        URLCandidate(url=country_url, domain="any-retailer.ch", title="Acme Widget 18 ks", organic_count=1, best_position=2),
        URLCandidate(url=global_url, domain="example.com", title="Acme Widget 18 ks", organic_count=1, best_position=1),
    ]
    cards = ranker.score(
        product=task,
        candidates=candidates,
        scrapes={country_url: country_scrape, global_url: global_scrape},
        verifications={country_url: country_verification, global_url: global_verification},
    )
    match = selector.select(
        task=task,
        scorecards=cards,
        termination_reason="test",
        budget_snapshot=BudgetTracker(max_organic=3, max_ai_mode=2, max_scrapes=2).snapshot(),
    )
    assert match.product_url == country_url
    assert match.country_check == "MATCHED"
