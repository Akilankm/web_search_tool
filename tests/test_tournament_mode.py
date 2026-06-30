from __future__ import annotations

from product_evidence_harness.budget import BudgetTracker
from product_evidence_harness.candidate_store import CandidateStore
from product_evidence_harness.config import HarnessPolicy, TournamentConfig
from product_evidence_harness.contracts import ActionType, MatchVerification, OrganicSearchResponse, OrganicSearchResult, ProductQuery, ProductSearchState, ScrapeResult
from product_evidence_harness.evidence_extractor import EvidenceExtractor
from product_evidence_harness.identity_verifier import ProductIdentityVerifier
from product_evidence_harness.production_url import ProductionURLGate
from product_evidence_harness.query_builder import QueryBuilder
from product_evidence_harness.ranker import ProductURLRanker
from product_evidence_harness.tournament import CandidateTournamentEngine


class FakeOrganicClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def search(self, query: str, **kwargs) -> OrganicSearchResponse:
        self.calls.append(query)
        results = [
            OrganicSearchResult(url="https://weak.example.com/product/weak", title="LEGO Friends school related item", snippet="related product", position=1, query=query),
            OrganicSearchResult(url="https://shop.example.cz/product/41731", title="LEGO Friends 41731 Heartlake International School", snippet="EAN 5702017415177", position=2, query=query),
            OrganicSearchResult(url="https://other.example.com/category/lego", title="LEGO category", snippet="listing", position=3, query=query),
        ]
        return OrganicSearchResponse(query=query, search_id="fake", status="Success", results=results)


class FakeScraper:
    def scrape_many(self, urls, *, product=None):
        return [self.scrape(url, product=product) for url in urls]

    def scrape(self, url, *, product=None):
        exact = "41731" in url
        return ScrapeResult(
            url=url,
            scraped=True,
            success=True,
            reachable=True,
            is_scrapable=True,
            status_code=200,
            final_url=url,
            title="LEGO Friends 41731 Heartlake International School" if exact else "LEGO Friends related school item",
            h1="LEGO Friends 41731 Heartlake International School" if exact else "LEGO school item",
            page_product_name="LEGO Friends 41731 Heartlake International School" if exact else "LEGO school item",
            structured_eans=("5702017415177",) if exact else (),
            brand="LEGO",
            manufacturer="LEGO",
            description="Detailed product page with school set information and accessories." if exact else "Related product page.",
            specs={"Set number": "41731"} if exact else {},
            image_urls=("https://shop.example.cz/41731.jpg",) if exact else (),
            richness_score=0.85 if exact else 0.35,
            word_count=350 if exact else 120,
            image_count=1 if exact else 0,
            looks_like_product_page=True,
            contains_ean=exact,
            text_overlap=0.95 if exact else 0.45,
        )


class FakeVerifier(ProductIdentityVerifier):
    def __init__(self) -> None:
        super().__init__(policy=HarnessPolicy())

    def verify(self, product, scrape, identity_graph=None):
        exact = "41731" in scrape.url
        return MatchVerification(
            url=scrape.url,
            identity_status="VERIFIED" if exact else "WEAK",
            ean_check="MATCHED" if exact else "UNKNOWN",
            title_check="STRONG" if exact else "WEAK",
            quantity_check="MATCHED",
            brand_check="MATCHED",
            page_type_check="PRODUCT_DETAIL",
            title_match_score=0.95 if exact else 0.45,
            exact_product_check="EXACT_MATCH" if exact else "UNKNOWN",
            variant_check="MATCHED",
            identity_driver="EAN_AND_TITLE" if exact else "TITLE_ONLY",
            page_gtins_valid=("5702017415177",) if exact else (),
            justifications=("test",),
        )


def _engine() -> CandidateTournamentEngine:
    return CandidateTournamentEngine(
        config=TournamentConfig(enabled=True, max_serp_credits=4, candidate_pool=20, preflight_top_k=10, batch_size=5, max_batches=2),
        query_builder=QueryBuilder(),
        organic_client=FakeOrganicClient(),
        candidate_store=CandidateStore(max_pool_size=20),
        scraper=FakeScraper(),
        verifier=FakeVerifier(),
        ranker=ProductURLRanker(policy=HarnessPolicy()),
        evidence_extractor=EvidenceExtractor(),
        production_gate=ProductionURLGate(),
    )


def test_tournament_mode_selects_exact_production_champion_under_four_serp_calls() -> None:
    product = ProductQuery(
        row_id="row-1",
        main_text="LEGO Friends 41731 Heartlake International School",
        country_code="CZ",
        retailer_name="Alza",
        ean="5702017415177",
    )
    state = ProductSearchState(task=product, budget=BudgetTracker(max_organic=4, max_ai_mode=0, max_scrapes=20))
    engine = _engine()

    result = engine.run(state)

    assert result.search_credits_used <= 4
    assert result.champion_url == "https://shop.example.cz/product/41731"
    assert result.champion_production_ready is True
    assert result.champion_status == "PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL"
    assert state.budget.organic_used <= 4
    assert state.scrapes
    assert any(a.action.action_type == ActionType.ORGANIC_SEARCH for a in state.actions_taken)


def test_query_builder_suppresses_invalid_ean_from_search_queries() -> None:
    product = ProductQuery(
        row_id="row-invalid-ean",
        main_text="COCHE DEPORTIVO RASTAR PORSCHE 911GT2RS 1/24 CON CONTROL",
        country_code="CO",
        retailer_name="Mercado Libre",
        ean="7800270000000",  # invalid GTIN checksum
    )
    query = QueryBuilder().requested_retailer_search(product)

    assert "7800270000000" not in query
    assert "RASTAR" in query or "rastar" in query.lower()
    assert "Mercado Libre" in query


def test_tournament_records_requested_retailer_scope_for_metrics() -> None:
    product = ProductQuery(
        row_id="row-retailer-scope",
        main_text="LEGO Friends 41731 Heartlake International School",
        country_code="CZ",
        retailer_name="Alza",
        ean="5702017415177",
    )
    state = ProductSearchState(task=product, budget=BudgetTracker(max_organic=4, max_ai_mode=0, max_scrapes=20))
    engine = _engine()

    engine.run(state)

    assert any(
        a.action.action_type == ActionType.ORGANIC_SEARCH
        and a.action.metadata.get("scope") == "requested_retailer"
        for a in state.actions_taken
    )
