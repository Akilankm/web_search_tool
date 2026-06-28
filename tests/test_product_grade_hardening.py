from __future__ import annotations

from product_evidence_harness import HarnessPolicy, ProductQuery
from product_evidence_harness.budget import BudgetTracker
from product_evidence_harness.config import SerpAPIConfig
from product_evidence_harness.contracts import CandidateScorecard, MatchVerification, ScrapeResult, URLCandidate
from product_evidence_harness.selector import FinalSelector
from product_evidence_harness.serp_clients import GoogleOrganicSearchClient


class CaptureOrganic(GoogleOrganicSearchClient):
    def __init__(self):
        super().__init__(SerpAPIConfig(api_key="k", country_code="ch", language_code="de"))
        self.params = None
    def _get(self, params):
        self.params = params
        return {"search_metadata": {"id": "x", "status": "Success"}, "organic_results": []}


def test_global_fallback_omits_country_gl_and_uses_requested_language():
    client = CaptureOrganic()
    client.search("exact product", product=ProductQuery(main_text="exact product", country_code="CH"), scope="global", language_code="en")
    assert "gl" not in client.params
    assert client.params["hl"] == "en"


def test_scientific_notation_ean_is_not_silently_recovered():
    product = ProductQuery(main_text="abc", country_code="CH", ean="7.61245E+12")
    assert product.ean is None
    assert product.input_validation_warnings


def test_hard_rejected_candidate_becomes_reference_not_product_url_by_default():
    url = "https://shop.ch/p/wrong"
    candidate = URLCandidate(url=url, domain="shop.ch", title="Wrong variant")
    scrape = ScrapeResult(url=url, scraped=True, success=True, reachable=True, is_scrapable=True, status_code=200, final_url=url, looks_like_product_page=True)
    verification = MatchVerification(
        url=url,
        identity_status="MISMATCH",
        ean_check="ABSENT",
        title_check="PARTIAL",
        quantity_check="UNKNOWN",
        brand_check="UNKNOWN",
        page_type_check="PRODUCT_DETAIL",
        title_match_score=0.3,
        variant_check="CONFLICT",
        blocking_reasons=("variant conflict",),
    )
    card = CandidateScorecard(
        candidate=candidate,
        organic_score=0.5,
        ai_score=0,
        retailer_score=0.5,
        country_score=1,
        ean_score=0,
        title_score=0.3,
        product_page_score=1,
        scrape_score=1,
        identity_score=0,
        richness_score=0.4,
        weighted_confidence=0.3,
        confidence_cap=0.05,
        final_confidence=0.05,
        validation_status="REJECTED",
        hard_failures=("variant conflict",),
        scrape=scrape,
        verification=verification,
        country_check="MATCHED",
    )
    result = FinalSelector(policy=HarnessPolicy()).select(
        task=ProductQuery(main_text="right variant", country_code="CH"),
        scorecards=[card],
        termination_reason="done",
        budget_snapshot=BudgetTracker(max_organic=1, max_ai_mode=0, max_scrapes=1).snapshot(),
    )
    assert result.product_url is None
    assert result.best_reference_url == url
    assert result.url_decision_status == "NO_ACCEPTABLE_URL_FOUND"
