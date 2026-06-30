from __future__ import annotations

from product_evidence_harness import ProductEvidenceHarness, ProductQuery, ProductSearchState, ProductURLMatch
from product_evidence_harness.budget import BudgetTracker
from product_evidence_harness.contracts import CandidateScorecard, MatchVerification, ScrapeResult, URLCandidate
from product_evidence_harness.production_url import ProductionURLGate


def _scrape(url: str, *, scrapable: bool = True, product_page: bool = True, rich: float = 0.80, words: int = 400) -> ScrapeResult:
    return ScrapeResult(
        url=url,
        scraped=True,
        success=True,
        reachable=True,
        is_scrapable=scrapable,
        status_code=200,
        final_url=url,
        title="LEGO Friends 41731 Heartlake International School",
        h1="LEGO Friends 41731 Heartlake International School",
        page_product_name="LEGO Friends 41731 Heartlake International School",
        structured_eans=("5702017415177",),
        has_price=True,
        brand="LEGO",
        manufacturer="LEGO",
        description="Detailed LEGO Friends school set with accessories and figures.",
        specs={"Set number": "41731"},
        image_urls=("https://retailer.test/41731.jpg",),
        richness_score=rich,
        word_count=words,
        image_count=1,
        looks_like_product_page=product_page,
        contains_ean=True,
        text_overlap=0.95,
    )


def _verification(url: str, *, exact: bool = True) -> MatchVerification:
    return MatchVerification(
        url=url,
        identity_status="VERIFIED" if exact else "UNVERIFIED",
        ean_check="MATCHED" if exact else "UNKNOWN",
        title_check="STRONG" if exact else "WEAK",
        quantity_check="MATCHED",
        brand_check="MATCHED",
        page_type_check="PRODUCT_PAGE",
        title_match_score=0.95 if exact else 0.30,
        exact_product_check="EXACT_MATCH" if exact else "UNKNOWN",
        variant_check="MATCHED",
        identity_driver="EAN_AND_TITLE" if exact else "UNKNOWN",
        page_gtins_valid=("5702017415177",) if exact else (),
    )


def _card(url: str, *, exact: bool = True, scrapable: bool = True, final_confidence: float = 0.95) -> CandidateScorecard:
    scrape = _scrape(url, scrapable=scrapable)
    verification = _verification(url, exact=exact)
    return CandidateScorecard(
        candidate=URLCandidate(url=url, title="LEGO Friends 41731", domain="retailer.test"),
        organic_score=1.0,
        ai_score=0.0,
        retailer_score=1.0,
        country_score=1.0,
        ean_score=1.0 if exact else 0.0,
        title_score=0.95 if exact else 0.30,
        product_page_score=1.0,
        scrape_score=1.0 if scrapable else 0.30,
        identity_score=1.0 if exact else 0.20,
        richness_score=scrape.richness_score,
        weighted_confidence=final_confidence,
        confidence_cap=1.0,
        final_confidence=final_confidence,
        validation_status="VERIFIED" if exact else "NEEDS_REVIEW",
        scrape=scrape,
        verification=verification,
        retailer_check="MATCHED",
        country_check="MATCHED",
        exact_product_check=verification.exact_product_check,
        variant_check=verification.variant_check,
    )


def _match(url: str) -> ProductURLMatch:
    return ProductURLMatch(
        row_id="row-1",
        main_text="LEGO Friends 41731 Heartlake International School",
        country_code="CZ",
        retailer_name="Alza",
        ean="5702017415177",
        product_url=url,
        best_available_url=url,
        verified_exact_url=None,
        confidence=0.50,
        validation_status="NEEDS_REVIEW",
        identity_status="WEAK",
        is_exact_product_match=False,
        match_reason="weak selected url",
        justification="initial weak result",
        needs_review=True,
    )


def test_production_gate_requires_browser_scrapable_exact_product_url() -> None:
    ready = ProductionURLGate().assess_card(_card("https://retailer.test/product/41731"))
    weak = ProductionURLGate().assess_card(_card("https://retailer.test/product/weak", exact=False, scrapable=True))

    assert ready.production_ready is True
    assert ready.browser_openable is True
    assert ready.highly_scrapable is True
    assert ready.exact_product_match is True
    assert ready.status == "PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL"

    assert weak.production_ready is False
    assert weak.exact_product_match is False
    assert weak.status == "PRODUCT_URL_NOT_EXACT_MATCH_NEEDS_REVIEW"


def test_pipeline_promotes_production_grade_url_over_weak_initial_product_url() -> None:
    weak_url = "https://retailer.test/product/weak"
    strong_url = "https://retailer.test/product/41731"
    state = ProductSearchState(
        task=ProductQuery(row_id="row-1", main_text="LEGO Friends 41731 Heartlake International School", country_code="CZ", retailer_name="Alza", ean="5702017415177"),
        budget=BudgetTracker(max_scrapes=10),
        scorecards=[_card(weak_url, exact=False, scrapable=True, final_confidence=0.60), _card(strong_url, exact=True, scrapable=True, final_confidence=0.96)],
    )

    selected = ProductEvidenceHarness._enforce_production_grade_product_url(_match(weak_url), state)

    assert selected.product_url == strong_url
    assert selected.verified_exact_url == strong_url
    assert selected.is_scrapable is True
    assert selected.is_exact_product_match is True
    assert selected.needs_review is False
    assert selected.url_decision_status == "PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL"


def test_pipeline_keeps_nonempty_url_but_marks_non_production_fallback() -> None:
    weak_url = "https://retailer.test/product/weak"
    state = ProductSearchState(
        task=ProductQuery(row_id="row-1", main_text="LEGO Friends 41731 Heartlake International School", country_code="CZ", retailer_name="Alza", ean="5702017415177"),
        budget=BudgetTracker(max_scrapes=10),
        scorecards=[_card(weak_url, exact=False, scrapable=True, final_confidence=0.60)],
    )

    selected = ProductEvidenceHarness._enforce_production_grade_product_url(_match(weak_url), state)

    assert selected.product_url == weak_url
    assert selected.needs_review is True
    assert selected.is_exact_product_match is False
    assert selected.primary_reject_reason == "PRODUCT_URL_NOT_PRODUCTION_GRADE"
    assert selected.url_decision_status == "PRODUCT_URL_NOT_EXACT_MATCH_NEEDS_REVIEW"
