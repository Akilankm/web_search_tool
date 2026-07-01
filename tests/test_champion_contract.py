from __future__ import annotations

from product_evidence_harness.contracts import CandidateScorecard, MatchVerification, ProductQuery, ProductSearchState, ProductURLMatch, ScrapeResult, URLCandidate
from product_evidence_harness.production_url import ProductionURLAssessment, ProductionURLGate
from product_evidence_harness.review_artifacts import ReviewArtifactWriter
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


def _card(url: str, *, exact: bool = False, rejected: bool = False) -> CandidateScorecard:
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
        looks_like_product_page=exact or rejected,
        richness_score=0.8 if exact else 0.27 if rejected else 0.25,
        word_count=300,
        description="Detailed product description with enough coding evidence." if exact else "Thin page.",
        brand="Brand" if exact else "",
        image_urls=("https://example.com/image.jpg",) if exact else (),
        image_count=1 if exact else 0,
    )
    verification = MatchVerification(
        url=url,
        identity_status="MISMATCH" if rejected else "VERIFIED" if exact else "WEAK",
        ean_check="NOT_PROVIDED",
        title_check="MISMATCH" if rejected else "STRONG",
        quantity_check="NOT_APPLICABLE",
        brand_check="MATCHED" if exact else "UNKNOWN",
        page_type_check="PRODUCT_DETAIL" if exact or rejected else "NON_PRODUCT",
        title_match_score=0.05 if rejected else 0.9,
        exact_product_check="MISMATCH" if rejected else "EXACT_MATCH" if exact else "WEAK_MATCH",
        variant_check="CONFLICT" if rejected else "MATCHED",
        variant_conflict_terms=("bmw_vs_mazda", "azul_vs_blanco") if rejected else (),
        blocking_reasons=("distinctive title tokens did not match",) if rejected else (),
    )
    return CandidateScorecard(
        candidate=candidate,
        organic_score=0.8,
        ai_score=0.0,
        retailer_score=1.0,
        country_score=1.0,
        ean_score=0.0,
        title_score=0.05 if rejected else 0.9,
        product_page_score=1.0 if exact or rejected else 0.0,
        scrape_score=0.8,
        identity_score=0.0 if rejected else 1.0 if exact else 0.5,
        richness_score=scrape.richness_score,
        weighted_confidence=0.8 if exact else 0.05 if rejected else 0.8,
        confidence_cap=1.0,
        final_confidence=0.8 if exact else 0.05 if rejected else 0.8,
        validation_status="REJECTED" if rejected else "VERIFIED" if exact else "NEEDS_REVIEW",
        hard_failures=("variant/product-form conflict",) if rejected else (),
        scrape=scrape,
        verification=verification,
        retailer_check="MATCHED",
        country_check="MATCHED",
        exact_product_check=verification.exact_product_check,
        variant_check=verification.variant_check,
        primary_reject_reason="variant/product-form conflict" if rejected else "",
    )


def _state_with_card(card: CandidateScorecard) -> ProductSearchState:
    product = ProductQuery(row_id="row", main_text="Candidate", country_code="CO", retailer_name="Example")
    state = ProductSearchState(task=product, budget=None, scorecards=[card])
    state.scrapes = {card.candidate.url: card.scrape}
    state.verifications = {card.candidate.url: card.verification}
    return state


def _match(card: CandidateScorecard | None, *, product_url: str | None = None, best_available_url: str | None = None) -> ProductURLMatch:
    return ProductURLMatch(
        row_id="row",
        main_text="Candidate",
        country_code="CO",
        retailer_name="Example",
        ean=None,
        product_url=product_url,
        confidence=card.final_confidence if card else 0.0,
        validation_status=card.validation_status if card else "NEEDS_REVIEW",
        identity_status=card.verification.identity_status if card and card.verification else "UNVERIFIED",
        is_exact_product_match=False,
        match_reason="candidate selected" if card else "no selected url",
        justification="candidate selected" if card else "no selected url",
        needs_review=True,
        best_available_url=best_available_url,
    )


def test_rejected_fallback_is_not_retained_as_best_review_url() -> None:
    rejected_candidate = _card("https://example.com/mazda-white", rejected=True)
    state = _state_with_card(rejected_candidate)
    match = _match(rejected_candidate, product_url=rejected_candidate.candidate.url, best_available_url=rejected_candidate.candidate.url)
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
        best_review_candidate_url=rejected_candidate.candidate.url,
        best_review_candidate_score=0.05,
        best_review_candidate_status="REJECTED",
    )

    aligned = TournamentAwareProductEvidenceHarness._align_final_with_tournament_result(harness, match, state, result)

    assert aligned.product_url is None
    assert aligned.verified_exact_url is None
    assert aligned.best_available_url is None
    assert aligned.best_reference_url is None
    assert aligned.needs_review is True
    assert aligned.primary_reject_reason == "NO_SAFE_REVIEW_CANDIDATE"
    assert aligned.url_decision_status == "NO_SAFE_REVIEW_CANDIDATE"


def test_safe_review_candidate_is_retained_but_not_product_url() -> None:
    review_candidate = _card("https://example.com/review-safe", exact=True)
    state = _state_with_card(review_candidate)
    match = _match(review_candidate, product_url=review_candidate.candidate.url, best_available_url=review_candidate.candidate.url)
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
    assert aligned.best_reference_url == review_candidate.candidate.url
    assert aligned.needs_review is True
    assert aligned.url_decision_status == "NO_PRODUCTION_READY_TOURNAMENT_CHAMPION"


def test_product_url_is_champion_when_production_ready_champion_exists() -> None:
    champion = _card("https://example.com/ready", exact=True)
    state = _state_with_card(champion)
    match = _match(None)
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


def test_review_artifact_does_not_mark_rejected_fallback_selected() -> None:
    rejected_candidate = _card("https://example.com/mazda-white", rejected=True)
    state = _state_with_card(rejected_candidate)
    state.final_result = _match(rejected_candidate, product_url=None, best_available_url=rejected_candidate.candidate.url)

    payload = ReviewArtifactWriter().decision_payload(state)
    rows = payload["candidate_decisions"]

    assert payload["decision"]["decision"] == "UNRESOLVED_REVIEW_REQUIRED"
    assert payload["decision"]["best_review_url"] is None
    assert rows[0]["selected"] is False
    assert rows[0]["decision"] == "REJECTED_OR_NOT_PROMOTED"
