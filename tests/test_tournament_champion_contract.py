from __future__ import annotations

from product_evidence_harness.budget import BudgetTracker
from product_evidence_harness.candidate_store import CandidateStore
from product_evidence_harness.config import HarnessPolicy, TournamentConfig
from product_evidence_harness.constants import PAGE_TYPE_NON_PRODUCT
from product_evidence_harness.contracts import OrganicSearchResponse, OrganicSearchResult, ProductQuery, ProductSearchState, ScrapeResult
from product_evidence_harness.evidence_extractor import EvidenceExtractor
from product_evidence_harness.production_url import ProductionURLGate
from product_evidence_harness.query_builder import QueryBuilder
from product_evidence_harness.ranker import ProductURLRanker
from product_evidence_harness.tournament_champion import ChampionContractTournamentEngine
from product_evidence_harness.tournament_verifier import TournamentProductIdentityVerifier


class FakeOrganicClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def search(self, query: str, **kwargs) -> OrganicSearchResponse:
        self.calls.append(query)
        return OrganicSearchResponse(
            query=query,
            search_id="fake",
            status="Success",
            results=[OrganicSearchResult(url="https://example.com/product/rastar", title="Rastar Porsche 911 GT2 RS 1/24 con control", snippet="remote control car", position=1, query=query)],
        )


class FakeScraper:
    def scrape_many(self, urls, *, product=None):
        return [self.scrape(u, product=product) for u in urls]

    def scrape(self, url, *, product=None):
        return ScrapeResult(
            url=url,
            scraped=True,
            success=True,
            reachable=True,
            is_scrapable=True,
            status_code=200,
            final_url=url,
            title="Rastar Porsche 911 GT2 RS 1/24 con control",
            h1="Rastar Porsche 911 GT2 RS",
            page_product_name="Rastar Porsche 911 GT2 RS 1/24",
            richness_score=0.65,
            word_count=150,
            image_count=1,
            looks_like_product_page=True,
            text_overlap=0.90,
        )


def test_invalid_ean_is_not_used_in_tournament_queries_and_scope_is_tagged() -> None:
    product = ProductQuery(
        row_id="row-invalid-ean",
        main_text="COCHE DEPORTIVO RASTAR PORSCHE 911GT2RS 1/24 CON CONTROL",
        country_code="CO",
        retailer_name="Mercado Libre",
        ean="7800270000000",  # invalid GTIN checksum
    )
    state = ProductSearchState(task=product, budget=BudgetTracker(max_organic=4, max_ai_mode=0, max_scrapes=20))
    engine = ChampionContractTournamentEngine(
        config=TournamentConfig(enabled=True, max_serp_credits=4, candidate_pool=20, preflight_top_k=10, batch_size=5, max_batches=1),
        query_builder=QueryBuilder(),
        organic_client=FakeOrganicClient(),
        candidate_store=CandidateStore(max_pool_size=20),
        scraper=FakeScraper(),
        verifier=TournamentProductIdentityVerifier(policy=HarnessPolicy()),
        ranker=ProductURLRanker(policy=HarnessPolicy()),
        evidence_extractor=EvidenceExtractor(),
        production_gate=ProductionURLGate(),
    )

    result = engine.run(state)

    assert result.search_credits_used <= 4
    assert all("7800270000000" not in q for q in state.queries)
    assert any("tournament_reason:requested_retailer" in c.source_types for c in state.candidates)
    assert any(a.action.metadata.get("scope") == "requested_retailer" for a in state.actions_taken)


def test_thin_generic_page_is_not_exact_product_detail() -> None:
    verifier = TournamentProductIdentityVerifier(policy=HarnessPolicy())
    product = ProductQuery(row_id="thin", main_text="RASTAR PORSCHE 911GT2RS 1/24 CON CONTROL", country_code="CO")
    scrape = ScrapeResult(
        url="https://articulo.mercadolibre.com.ar/MLA-123-rastar-porsche-911gt2rs",
        scraped=True,
        success=True,
        reachable=True,
        is_scrapable=True,
        status_code=302,
        final_url="https://articulo.mercadolibre.com.ar/MLA-123-rastar-porsche-911gt2rs",
        title="Mercado Libre",
        page_product_name="Mercado Libre logo image",
        richness_score=0.10,
        word_count=10,
        looks_like_product_page=False,
    )

    verification = verifier.verify(product, scrape)

    assert verification.page_type_check == PAGE_TYPE_NON_PRODUCT
    assert verification.exact_product_check != "EXACT_MATCH"
