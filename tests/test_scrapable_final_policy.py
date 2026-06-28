from __future__ import annotations

from product_evidence_harness import HarnessBudgetConfig, HarnessConfig, ProductEvidenceHarness, ProductQuery, SerpAPIConfig
from product_evidence_harness.contracts import OrganicSearchResponse, OrganicSearchResult, ScrapeResult, SerpAIResponse


class OneCandidateOrganic:
    def __init__(self, url: str = "https://shop.cz/product/acme-widget-18-ks"):
        self.url = url

    def search(self, query, *, product=None):
        return OrganicSearchResponse(
            query=query,
            search_id="fake",
            status="Success",
            results=[
                OrganicSearchResult(
                    url=self.url,
                    title="Acme Widget 18 ks",
                    snippet="Buy Acme Widget 18 ks",
                    position=1,
                    query=query,
                )
            ],
        )


class NoCandidateOrganic:
    def search(self, query, *, product=None):
        return OrganicSearchResponse(query=query, search_id="fake", status="Success", results=[])


class FinalUrlAI:
    def search(self, query, *, product=None):
        return SerpAIResponse(
            query=query,
            status="Success",
            search_id="ai",
            markdown="FINAL_URL: https://ai.example.com/acme-widget-18-ks",
        )


class NonScrapableScraper:
    def scrape(self, url, *, product=None):
        return ScrapeResult(
            url=url,
            scraped=True,
            success=False,
            reachable=False,
            is_scrapable=False,
            status_code=None,
            final_url=url,
            title="",
            h1="",
            page_product_name="",
            richness_score=0.0,
            word_count=0,
            markdown_chars=0,
            looks_like_product_page=False,
            verification_text="",
            error="blocked or empty page",
        )


def _harness(*, organic, scraper, max_iterations=5):
    config = HarnessConfig(
        budget=HarnessBudgetConfig(
            max_organic_searches=1,
            max_ai_mode_searches=1,
            max_scrapes=2,
            max_iterations=max_iterations,
        )
    )
    return ProductEvidenceHarness(
        serp_config=SerpAPIConfig(api_key="test"),
        config=config,
        organic_client=organic,
        ai_client=FinalUrlAI(),
        scraper=scraper,
    )


def test_best_available_url_is_returned_when_candidate_is_not_scrapable():
    harness = _harness(organic=OneCandidateOrganic(), scraper=NonScrapableScraper())
    trace = harness.run(ProductQuery(main_text="Acme Widget 18 ks", country_code="CZ"), return_trace=True)

    assert trace.best_match.product_url == "https://shop.cz/product/acme-widget-18-ks"
    assert trace.best_match.verified_exact_url is None
    assert trace.best_match.url_decision_status == "BEST_AVAILABLE_NOT_SCRAPABLE"
    assert trace.best_match.needs_review is True
    assert trace.best_match.is_scrapable is False
    assert trace.best_match.availability_inference == "UNKNOWN"


def test_ai_candidate_is_returned_as_best_available_without_successful_scrape():
    harness = _harness(organic=NoCandidateOrganic(), scraper=NonScrapableScraper(), max_iterations=4)
    trace = harness.run(ProductQuery(main_text="Acme Widget 18 ks", country_code="CZ"), return_trace=True)

    assert trace.best_match.product_url == "https://ai.example.com/acme-widget-18-ks"
    assert trace.best_match.verified_exact_url is None
    assert trace.best_match.needs_review is True
