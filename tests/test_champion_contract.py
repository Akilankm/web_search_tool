from __future__ import annotations

from dataclasses import replace

from product_evidence_harness.config import HarnessConfig, HarnessPolicy, SerpAPIConfig, TournamentConfig
from product_evidence_harness.contracts import CandidateScorecard, MatchVerification, ProductQuery, ProductSearchState, ProductURLMatch, ScrapeResult, URLCandidate
from product_evidence_harness.production_url import ProductionURLAssessment, ProductionURLGate
from product_evidence_harness.tournament import TournamentResult
from product_evidence_harness.tournament_pipeline import TournamentAwareProductEvidenceHarness


class FakeProductionGate(ProductionURLGate):
    def assess_card(self, card):
        ready = card.candidate.url.endswith("/ready")
        return ProductionURLAssessment(
            url=card.candidate.url,
            production_ready=ready,
            browser_openable=bool(card.scrape and card.scrape.reachable),
            highly_scrapable=bool(card.scrape and card.scrape.looks_like_product_page),
            exact_product_match=ready,
            status="PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL" if ready else "PRODUCT_URL_NOT_HIGHLY_SCRAPABLE_NEEDS_REVIEW",
            reasons=() if ready else ("URL_NOT_HIGHLY_SCRAPABLE",),
            score=0.95 if ready else 0.61,
        )


def _card(url: str, *, exact: bool = False) -> CandidateScorecard:
    candidate = URLCandidate(url=url, title="Champion", domain="example.com")
    scrape = ScrapeResult(
        url=url,
        scraped=True,
        success=True,
        reachable=True,
        is_scrapable=True,
        status_code=200,
        final_url=url,
        title="Champion",
        page_product_name="Champion",
        looks_like_product_page=exact,
        richness_score=0.8 if exact else 0.25,
        word_count=300,
    )
    verification = MatchVerification(
        url=url,
        identity_status="VERIFIED" if exact else "WEAK",
        ean_check="NOT_PROVIDED",
        title_check="STRONG",
        quantity_check="NOT_APPLICABLE",
        brand_check="MATCHED",
        page_type_check="PRODUCT_DETAIL" if exact else "NON_PRODUCT",
        title_match_score=0.9,
        exact_product_check="EXACT_MATCH" if exact else "WEAK_MATCH",
        variant_check="MATCHED",
    )
    return CandidateScorecard(
        candidate=candidate,
        organic_score=0.8,
        ai_score=0.0,
        retailer_score=1.0,
        country_score=1.0,
        ean_score=0.0,
        title_score=0.9,
        product_page_score=1.0 if exact else 0.0,
        scrape_score=0.8,
        identity_score=1.0 if exact else 0.5,
        richness_score=scrape.richness_score,
        weighted_confidence=0.8,
        confidence_cap=1.0,
        final_confidence=0.8,
        validation_status="VERIFIED" if exact else "NEEDS_REVIEW",
        scrape=scrape,
        verification=verification,
        retailer_check="MATCHED",
        country_check="MATCHED",
        exact_product_check=verification.exact_product_check,
        variant_check="MATCHED",
    )


def test_final_product_url_is_tournament_champion_even_when_not_production_ready() -> None:
    champion = _card("https://example.com/champion", exact=False)
    fallback = _card("https://example.com/ready", exact=True)
    product = ProductQuery(row_id="row", main_text="Champion", country_code="CO", retailer_name="Example")
    state = ProductSearchState(task=product, budget=None, scorecards=[champion, fallback])
    state.scrapes = {champion.candidate.url: champion.scrape, fallback.candidate.url: fallback.scrape}
    state.verifications = {champion.candidate.url: champion.verification, fallback.candidate.url: fallback.verification}
    match = ProductURLMatch(
        row_id="row",
        main_text="Champion",
        country_code="CO",
        retailer_name="Example",
        ean=None,
        product_url=fallback.candidate.url,
        confidence=0.95,
        validation_status="VERIFIED",
        identity_status="VERIFIED",
        is_exact_product_match=True,
        match_reason="fallback selected",
        justification="fallback selected",
        needs_review=False,
        verified_exact_url=fallback.candidate.url,
        best_available_url=fallback.candidate.url,
    )
    harness = object.__new__(TournamentAwareProductEvidenceHarness)
    harness.production_gate = FakeProductionGate()
    result = TournamentResult(
        enabled=True,
        search_credit_limit=4,
        search_credits_used=1,
        raw_candidate_count=2,
        preflight_candidate_count=2,
        scraped_candidate_count=2,
        champion_url=champion.candidate.url,
        champion_score=0.61,
        champion_status="PRODUCT_URL_NOT_HIGHLY_SCRAPABLE_NEEDS_REVIEW",
        champion_production_ready=False,
        runner_up_url=fallback.candidate.url,
    )

    aligned = TournamentAwareProductEvidenceHarness._align_final_with_tournament_champion(harness, match, state, result)

    assert aligned.product_url == champion.candidate.url
    assert aligned.verified_exact_url is None
    assert aligned.needs_review is True
    assert aligned.primary_reject_reason == "TOURNAMENT_CHAMPION_NOT_PRODUCTION_READY"
    assert aligned.url_decision_status == "PRODUCT_URL_NOT_HIGHLY_SCRAPABLE_NEEDS_REVIEW"
