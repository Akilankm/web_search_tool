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
from product_evidence_harness.contracts import OrganicSearchResponse, OrganicSearchResult, ScrapeResult


class FakeOrganicClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def search(self, query, *, product=None, **kwargs):
        self.calls.append(query)
        return OrganicSearchResponse(
            query=query,
            search_id="one-credit",
            status="Success",
            results=[
                OrganicSearchResult(
                    url="https://shop.ch/acme-rocket-18-pieces",
                    title="Acme Rocket 18 pieces",
                    snippet="Acme Rocket 18 pieces 4002051612345",
                    source="organic_results",
                    position=1,
                    query=query,
                ),
                OrganicSearchResult(
                    url="https://manufacturer.example/acme-rocket-18-pieces",
                    title="Acme Rocket 18 pieces specifications",
                    snippet="Official product specifications 4002051612345",
                    source="product_sites",
                    position=1,
                    query=query,
                ),
            ],
        )


class FakeScraper:
    def scrape_many(self, urls, *, product=None, max_workers=None):
        return [self.scrape(url, product=product) for url in urls]

    def scrape(self, url, *, product=None):
        retailer = "shop.ch" in url
        specs = {"Brand": "Acme", "Recommended age": "8 years"} if retailer else {"Material": "ABS plastic"}
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
            structured_eans=("4002051612345",),
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
            markdown_excerpt="Acme Rocket 18 pieces 4002051612345 Brand Acme Recommended age 8 years Material ABS plastic",
            markdown_chars=1200,
            word_count=220,
            image_count=1,
            looks_like_product_page=True,
            contains_ean=True,
            text_overlap=1.0,
            verification_text="Acme Rocket 18 pieces 4002051612345 add to cart Brand Acme Recommended age 8 years Material ABS plastic",
        )


def test_one_credit_search_and_multi_url_feature_coverage(tmp_path):
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
        one_credit=OneCreditConfig(output_dir=str(tmp_path), write_outputs=False, scrape_top_k=2),
        organic_client=organic,
        scraper=FakeScraper(),
    )
    result = harness.run(
        ProductQuery(
            row_id="toy-001",
            main_text="Acme Rocket 18 pieces",
            country_code="CH",
            retailer_name="shop.ch",
            ean="4002051612345",
        ),
        feature_schema=schema,
        return_trace=True,
    )

    assert len(organic.calls) == 1
    assert result.best_match.organic_calls_used == 1
    assert result.evidence_set is not None
    assert result.evidence_set.primary_url == "https://shop.ch/acme-rocket-18-pieces"
    assert result.evidence_set.supplementary_urls == ("https://manufacturer.example/acme-rocket-18-pieces",)
    assert result.evidence_set.required_coverage == 1.0
    assert result.evidence_set.coding_ready is True
