from __future__ import annotations

from product_evidence_harness import HarnessBudgetConfig, HarnessConfig, ProductEvidenceHarness, ProductQuery, SerpAPIConfig
from product_evidence_harness.contracts import OrganicSearchResponse, OrganicSearchResult, ScrapeResult, SerpAIResponse


class FakeOrganic:
    def __init__(self):
        self.calls = []

    def search(self, query, *, product=None):
        self.calls.append(query)
        return OrganicSearchResponse(
            query=query,
            search_id="fake",
            status="Success",
            results=[OrganicSearchResult(url="https://shop.cz/product/acme-widget-18-ks", title="Acme Widget 18 ks", snippet="Buy Acme Widget 18 ks", position=1, query=query)],
        )


class FakeAI:
    def search(self, query, *, product=None):
        return SerpAIResponse(query=query, status="Success", search_id="ai", markdown="FINAL_URL: https://shop.cz/product/acme-widget-18-ks")


class FakeScraper:
    def scrape(self, url, *, product=None):
        return ScrapeResult(
            url=url, scraped=True, success=True, reachable=True, is_scrapable=True, status_code=200,
            final_url=url, title="Acme Widget 18 ks", h1="Acme Widget 18 ks", page_product_name="Acme Widget 18 ks",
            structured_eans=("4002051612345",), richness_score=0.8, word_count=200, markdown_chars=1000,
            looks_like_product_page=True, verification_text="Acme Widget 18 ks 4002051612345 add to cart",
        )


def test_harness_search_scrape_converges_to_verified():
    config = HarnessConfig(budget=HarnessBudgetConfig(max_organic_searches=2, max_ai_mode_searches=2, max_scrapes=2, max_iterations=5))
    harness = ProductEvidenceHarness(
        serp_config=SerpAPIConfig(api_key="test"),
        config=config,
        organic_client=FakeOrganic(),
        ai_client=FakeAI(),
        scraper=FakeScraper(),
    )
    trace = harness.run(ProductQuery(main_text="Acme Widget 18 ks", country_code="CZ", ean="4002051612345"), return_trace=True)
    assert trace.best_match.validation_status == "VERIFIED"
    assert trace.best_match.product_url == "https://shop.cz/product/acme-widget-18-ks"
    assert trace.best_match.scrape_calls_used == 1
    assert [r.action.action_type.value for r in trace.state.actions_taken][:2] == ["organic_search", "scrape_url"]
