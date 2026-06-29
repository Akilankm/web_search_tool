from __future__ import annotations

from product_evidence_harness.budget import BudgetTracker
from product_evidence_harness.config import HarnessBudgetConfig, HarnessConfig
from product_evidence_harness.contracts import (
    ActionType,
    AgentAction,
    MatchVerification,
    ProductEvidence,
    ProductQuery,
    ProductSearchState,
    ScrapeResult,
    URLCandidate,
)
from product_evidence_harness.country_profiles import CountryProfileRegistry
from product_evidence_harness.executor import HarnessExecutor
from product_evidence_harness.planner import HarnessPlanner
from product_evidence_harness.query_builder import QueryBuilder
from product_evidence_harness.scraper import CrawlScraper


def _scrape(url: str) -> ScrapeResult:
    return ScrapeResult(
        url=url,
        scraped=True,
        success=True,
        reachable=True,
        is_scrapable=True,
        status_code=200,
        final_url=url,
        looks_like_product_page=True,
        page_product_name="demo product",
        richness_score=0.5,
    )


def test_scrape_many_preserves_input_order(monkeypatch) -> None:
    scraper = CrawlScraper(scrape_concurrency=3, static_fetch_first=False)
    urls = ["https://shop.example/p/1", "https://shop.example/p/2", "https://shop.example/p/3"]

    def fake_scrape(url: str, *, product=None):
        return _scrape(url)

    monkeypatch.setattr(scraper, "scrape", fake_scrape)

    results = scraper.scrape_many(urls, product=ProductQuery(main_text="demo", country_code="US"))

    assert [r.url for r in results] == urls


def test_planner_returns_scrape_batch_for_multiple_country_candidates() -> None:
    country_profiles = CountryProfileRegistry.load()
    config = HarnessConfig(
        budget=HarnessBudgetConfig(max_scrapes=10),
        enable_llm_search_planning=False,
        max_country_scrapes_per_batch=3,
    )
    planner = HarnessPlanner(config=config, query_builder=QueryBuilder(country_profiles=country_profiles), country_profiles=country_profiles)
    product = ProductQuery(row_id="row-1", main_text="demo product", country_code="US")
    state = ProductSearchState(
        task=product,
        budget=BudgetTracker(max_scrapes=10),
        candidates=[
            URLCandidate(url="https://example.com/product/1", domain="example.com"),
            URLCandidate(url="https://example.com/product/2", domain="example.com"),
            URLCandidate(url="https://example.com/product/3", domain="example.com"),
        ],
    )

    action = planner.next_action(state)

    assert action.action_type == ActionType.SCRAPE_URL
    assert action.metadata["batch_size"] == 3
    assert list(action.metadata["urls"]) == [
        "https://example.com/product/1",
        "https://example.com/product/2",
        "https://example.com/product/3",
    ]


class FakeScraper:
    def scrape_many(self, urls, *, product=None):
        return [_scrape(url) for url in urls]


class FakeEvidenceExtractor:
    def from_scrape(self, scrape):
        return ProductEvidence(source_url=scrape.url, source_type="scrape")


class FakeVerifier:
    def verify(self, product, scrape, *, identity_graph=None):
        return MatchVerification(
            url=scrape.url,
            identity_status="UNVERIFIED",
            ean_check="NOT_PROVIDED",
            title_check="WEAK",
            quantity_check="NOT_APPLICABLE",
            brand_check="UNKNOWN",
            page_type_check="UNKNOWN",
            title_match_score=0.0,
        )


class FakeRanker:
    def score(self, *, product, candidates, scrapes, verifications):
        return []


class FakeClient:
    pass


def test_executor_scrape_batch_records_all_results() -> None:
    executor = HarnessExecutor(
        organic_client=FakeClient(),
        ai_client=FakeClient(),
        scraper=FakeScraper(),
        candidate_store=None,
        verifier=FakeVerifier(),
        ranker=FakeRanker(),
        evidence_extractor=FakeEvidenceExtractor(),
    )
    product = ProductQuery(row_id="row-1", main_text="demo product", country_code="US")
    state = ProductSearchState(task=product, budget=BudgetTracker(max_scrapes=10))
    urls = ["https://example.com/product/1", "https://example.com/product/2"]
    action = AgentAction(ActionType.SCRAPE_URL, "batch scrape", metadata={"urls": tuple(urls), "scope": "country"})

    summary = executor.execute(action, state)

    assert summary["urls_scraped"] == 2
    assert summary["scrapable_count"] == 2
    assert set(state.scrapes) == set(urls)
    assert set(state.verifications) == set(urls)
    assert state.budget.scrape_used == 2
