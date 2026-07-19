from __future__ import annotations

from product_evidence_harness import (
    FeatureAwareProductEvidenceHarness,
    FeatureCriticality,
    FeatureDefinition,
    FeatureSchema,
    HarnessConfig,
    OneCreditConfig,
    ProductQuery,
    SerpAPIConfig,
)
from product_evidence_harness.adaptive_search import SearchAction, SearchObservation
from product_evidence_harness.contracts import OrganicSearchResponse, OrganicSearchResult, ScrapeResult


VALID_EAN = "4002051612344"


class FakeOrganicClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def search(self, query, *, product=None, **kwargs):
        self.calls.append({"query": query, **kwargs})
        return OrganicSearchResponse(
            query=query,
            search_id="adaptive-search",
            status="Success",
            results=[
                OrganicSearchResult(
                    url="https://shop.ch/acme-rocket-18-pieces",
                    title="Acme Rocket 18 pieces",
                    snippet=f"Acme Rocket 18 pieces {VALID_EAN}",
                    source="organic_results",
                    position=1,
                    query=query,
                ),
                OrganicSearchResult(
                    url="https://manufacturer.example/acme-rocket-18-pieces",
                    title="Acme Rocket 18 pieces specifications",
                    snippet=f"Official product specifications {VALID_EAN}",
                    source="product_sites",
                    position=1,
                    query=query,
                ),
            ],
        )


class FakeAdaptivePlanner:
    def __init__(self) -> None:
        self.calls = 0
        self.fallbacks = 0

    def choose_action(self, *, product, credit_number, **kwargs):
        self.calls += 1
        if credit_number == 1:
            return SearchAction(
                engine="google",
                purpose="requested_retailer_direct_url",
                query=f'"{product.main_text}" "{product.retailer_name}"',
                scope="country",
                country_code=product.country_code,
                planner_source="llm",
            )
        if credit_number == 2:
            return SearchAction(
                engine="google_shopping",
                purpose="country_alternative_product_resolution",
                query=f'"{product.main_text}"',
                scope="country",
                country_code=product.country_code,
                planner_source="llm",
            )
        return SearchAction(
            engine="google_ai_mode",
            purpose="global_exact_product_confirmation",
            query=f'"{product.main_text}" exact product page',
            scope="global",
            country_code=product.country_code,
            planner_source="llm",
        )


class FakeAdaptiveRouter:
    def __init__(self, organic: FakeOrganicClient) -> None:
        self.organic = organic

    def execute(self, action, product):
        response = self.organic.search(
            action.query,
            product=product,
            scope=action.scope,
            language_code=action.language_code or product.language_code,
            exclude_retailer=action.purpose != "requested_retailer_direct_url",
        )
        return SearchObservation(
            action=action,
            status=response.status,
            search_id=response.search_id,
            results=response.results,
            raw_result_count=len(response.results),
            external_url_count=len(response.results),
            raw_payload=response.raw,
        )


class FakeScraper:
    def scrape_many(self, urls, *, product=None, max_workers=None):
        return [self.scrape(url, product=product) for url in urls]

    def scrape(self, url, *, product=None):
        retailer = "shop.ch" in url
        specs = (
            {"Brand": "Acme", "Recommended age": "8 years"}
            if retailer
            else {"Brand": "Acme", "Material": "ABS plastic"}
        )
        feature_text = (
            "Brand Acme Recommended age 8 years"
            if retailer
            else "Brand Acme Material ABS plastic"
        )
        return ScrapeResult(
            url=url,
            scraped=True,
            success=True,
            reachable=True,
            is_scrapable=True,
            status_code=200,
            final_url=url,
            title="Acme Rocket 18 pieces",
            h1="Acme Rocket 18 pieces",
            page_product_name="Acme Rocket 18 pieces",
            structured_eans=(VALID_EAN,),
            has_price=retailer,
            price=29.99 if retailer else None,
            currency="CHF" if retailer else "",
            availability="InStock" if retailer else "",
            brand="Acme",
            manufacturer="Acme Toys",
            description="Acme Rocket 18 pieces is the exact construction toy product. " * 3,
            specs=specs,
            image_urls=("https://cdn.example/acme.jpg",),
            richness_score=0.90,
            markdown_excerpt=f"Acme Rocket 18 pieces {VALID_EAN} {feature_text}",
            markdown_chars=1200,
            word_count=220,
            image_count=1,
            looks_like_product_page=True,
            contains_ean=True,
            text_overlap=1.0,
            verification_text=f"Acme Rocket 18 pieces {VALID_EAN} add to cart {feature_text}",
        )


def test_adaptive_search_and_multi_url_diagnostic_coverage(tmp_path, monkeypatch):
    # Force all three synthetic credits so the test can verify cross-source
    # feature coverage independently of the production early-stop optimization.
    monkeypatch.setenv("PRODUCT_HARNESS_EARLY_STOP_ON_WORKING_URL", "false")
    organic = FakeOrganicClient()
    schema = FeatureSchema(
        schema_id="toy",
        required_coverage_threshold=1.0,
        features=(
            FeatureDefinition("BRAND", "Brand", criticality=FeatureCriticality.CRITICAL),
            FeatureDefinition("AGE", "Recommended age", criticality=FeatureCriticality.REQUIRED),
            FeatureDefinition("MATERIAL", "Material", criticality=FeatureCriticality.REQUIRED),
        ),
    )
    harness = FeatureAwareProductEvidenceHarness(
        serp_config=SerpAPIConfig(api_key="test", max_retries=3),
        config=HarnessConfig(write_outputs=False),
        one_credit=OneCreditConfig(
            output_dir=str(tmp_path),
            write_outputs=False,
            scrape_top_k=2,
        ),
        organic_client=organic,
        scraper=FakeScraper(),
    )
    harness.adaptive_search_planner = FakeAdaptivePlanner()
    harness.adaptive_search_router = FakeAdaptiveRouter(organic)

    result = harness.run(
        ProductQuery(
            row_id="toy-001",
            main_text="Acme Rocket 18 pieces",
            country_code="CH",
            retailer_name="shop.ch",
            ean=VALID_EAN,
        ),
        feature_schema=schema,
        return_trace=True,
    )

    assert len(organic.calls) == 3
    assert [call["scope"] for call in organic.calls] == ["country", "country", "global"]
    assert "official manufacturer" in organic.calls[0]["query"].lower()
    assert "shop.ch" not in organic.calls[0]["query"]
    assert "shop.ch" in organic.calls[1]["query"]
    assert "shop.ch" not in organic.calls[2]["query"]
    assert result.best_match.organic_calls_used == 3
    assert result.evidence_set is not None
    assert result.evidence_set.primary_url == "https://shop.ch/acme-rocket-18-pieces"
    assert result.evidence_set.supplementary_urls == (
        "https://manufacturer.example/acme-rocket-18-pieces",
    )
    assert result.evidence_set.required_coverage == 1.0
    assert result.evidence_set.coding_ready is True
