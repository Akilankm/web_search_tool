from __future__ import annotations

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
            highly_scrapable=ready,
            exact_product_match=ready,
            status="PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL" if ready else "PRODUCT_URL_CRITICAL_DETAILS_NOT_EXTRACTED_NEEDS_REVIEW",
            reasons=() if ready else ("CRITICAL_PRODUCT_DETAILS_NOT_EXTRACTED",),
            score=0.95 if ready else 0.61,
            critical_product_evidence_complete=ready,
        )


def _card(url: str, *, exact: bool = False) -> CandidateScorecard:
    candidate = URLCandidate(url=url, title="Candidate", domain="example.com")
    scrape = ScrapeResult(
        url=url,
        scraped=True,
        success=True,
        reachable=True,
        is_scrapable=True,
        status_code=200,
        final_url=url,
        title="Candidate",
        page_product_name="Candidate",
        looks_like_product_page=exact,
        richness_score=0.8 if exact else 0.25,
        word_count=300,
        description="Detailed product description with enough coding evidence." if exact else "Thin page.",
        brand="Brand" if exact else "",
        image_urls=("https://example.com/image.jpg",) if exact else (),
        image_count=1 if exact else 0,
    )
    verification = MatchVerification(
        url=url,
        identity_status="VERIFIED" if exact else "WEAK",
        ean_check="NOT_PROVIDED",
        title_check="STRONG",
        quantity_check="NOT_APPLICABLE",
        brand_check="MATCHED" if exact else "UNKNOWN",
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


def test_no_product_url_when_no_production_ready_champion_exists() -> None:
    review_candidate = _card("https://example.com/review", exact=False)
    product = ProductQuery(row_id="row", main_text="Candidate", country_code="CO", retailer_name="Example")
    state = ProductSearchState(task=product, budget=None, scorecards=[review_candidate])
    state.scrapes = {review_candidate.candidate.url: review_candidate.scrape}
    state.verifications = {review_candidate.candidate.url: review_candidate.verification}
    match = ProductURLMatch(
        row_id="row",
        main_text="Candidate",
        country_code="CO",
        retailer_name="Example",
        ean=None,
        product_url=review_candidate.candidate.url,
        confidence=0.61,
        validation_status="NEEDS_REVIEW",
        identity_status="WEAK",
        is_exact_product_match=False,
        match_reason="review candidate selected",
        justification="review candidate selected",
        needs_review=True,
        best_available_url=review_candidate.candidate.url,
    )
    harness = object.__new__(TournamentAwareProductEvidenceHarness)
    harness.production_gate = FakeProductionGate()
    result = TournamentResult(
        enabled=True,
        search_credit_limit=4,
        search_credits_used=1,
        raw_candidate_count=1,
        preflight_candidate_count=1,
        scraped_candidate_count=1,
        champion_url=None,
        champion_status="NO_PRODUCTION_READY_CHAMPION",
        champion_production_ready=False,
        best_review_candidate_url=review_candidate.candidate.url,
        best_review_candidate_score=0.61,
        best_review_candidate_status="PRODUCT_URL_CRITICAL_DETAILS_NOT_EXTRACTED_NEEDS_REVIEW",
    )

    aligned = TournamentAwareProductEvidenceHarness._align_final_with_tournament_result(harness, match, state, result)

    assert aligned.product_url is None
    assert aligned.verified_exact_url is None
    assert aligned.best_available_url == review_candidate.candidate.url
    assert aligned.needs_review is True
    assert aligned.primary_reject_reason == "NO_PRODUCTION_READY_TOURNAMENT_CHAMPION"
    assert aligned.url_decision_status == "NO_PRODUCTION_READY_TOURNAMENT_CHAMPION"


def test_product_url_is_champion_when_production_ready_champion_exists() -> None:
    champion = _card("https://example.com/ready", exact=True)
    product = ProductQuery(row_id="row", main_text="Candidate", country_code="CO", retailer_name="Example")
    state = ProductSearchState(task=product, budget=None, scorecards=[champion])
    state.scrapes = {champion.candidate.url: champion.scrape}
    state.verifications = {champion.candidate.url: champion.verification}
    match = ProductURLMatch(
        row_id="row",
        main_text="Candidate",
        country_code="CO",
        retailer_name="Example",
        ean=None,
        product_url=None,
        confidence=0.0,
        validation_status="NEEDS_REVIEW",
        identity_status="UNVERIFIED",
        is_exact_product_match=False,
        match_reason="no selected url",
        justification="no selected url",
        needs_review=True,
    )
    harness = object.__new__(TournamentAwareProductEvidenceHarness)
    harness.production_gate = FakeProductionGate()
    result = TournamentResult(
        enabled=True,
        search_credit_limit=4,
        search_credits_used=1,
        raw_candidate_count=1,
        preflight_candidate_count=1,
        scraped_candidate_count=1,
        champion_url=champion.candidate.url,
        champion_score=0.95,
        champion_status="PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL",
        champion_production_ready=True,
    )

    aligned = TournamentAwareProductEvidenceHarness._align_final_with_tournament_result(harness, match, state, result)

    assert aligned.product_url == champion.candidate.url
    assert aligned.verified_exact_url == champion.candidate.url
    assert aligned.needs_review is False
    assert aligned.url_decision_status == "PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL"
