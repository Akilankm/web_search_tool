from __future__ import annotations

from src.product_evidence_harness.browser_contracts import (
    BrowserEvidenceBundle,
    BrowserEvidenceStatus,
)
from src.product_evidence_harness.config import HarnessConfig, SerpAPIConfig
from src.product_evidence_harness.contracts import (
    CandidateScorecard,
    MatchVerification,
    OrganicSearchResponse,
    ProductQuery,
    ScrapeResult,
    URLCandidate,
)
from src.product_evidence_harness.feature_schema import (
    FeatureCriticality,
    FeatureDefinition,
    FeatureEvidence,
    FeatureEvidenceStatus,
    FeatureSchema,
    URLFeatureAssessment,
)
from src.product_evidence_harness.one_credit_pipeline import OneCreditConfig
from src.product_evidence_harness.strict_acceptance import StrictPrimaryURLSelector
from src.product_evidence_harness.three_stage_pipeline import ThreeStageProductEvidenceHarness
from src.product_evidence_harness.url_durability import ProductURLDurabilityGate


class RecordingOrganicClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def search(self, query: str, **kwargs) -> OrganicSearchResponse:
        self.calls.append({"query": query, **kwargs})
        return OrganicSearchResponse(
            query=query,
            search_id=None,
            status="Success",
            results=[],
            raw={},
        )


def test_three_stage_campaign_searches_manufacturer_before_requested_retailer() -> None:
    client = RecordingOrganicClient()
    harness = ThreeStageProductEvidenceHarness(
        serp_config=SerpAPIConfig(api_key="x" * 24),
        config=HarnessConfig(write_outputs=False, max_candidate_pool=90),
        one_credit=OneCreditConfig(
            write_outputs=False,
            max_candidates=90,
            scrape_top_k=2,
        ),
        organic_client=client,
        scraper=object(),
    )
    harness.scrape_top_k_per_stage = 2

    result = harness.run(
        ProductQuery(
            row_id="ROW-1",
            main_text="BMW M3 Wagon Hot Wheels 1:64 blue",
            country_code="CO",
            retailer_name="Mercado Libre",
            ean=None,
        ),
        return_trace=True,
    )

    assert result.state.budget.organic_used == 3
    assert [call["scope"] for call in client.calls] == ["country", "country", "global"]
    assert "official manufacturer" in client.calls[0]["query"].lower()
    assert "mercado libre" not in client.calls[0]["query"].lower()
    assert "mercado libre" in client.calls[1]["query"].lower()
    assert "mercado libre" not in client.calls[2]["query"].lower()
    assert [stage["name"] for stage in result.state.search_stage_trace] == [
        "manufacturer_primary",
        "requested_retailer_country",
        "global_fallback",
    ]


def test_three_stage_campaign_supports_optional_retailer_and_ean() -> None:
    client = RecordingOrganicClient()
    harness = ThreeStageProductEvidenceHarness(
        serp_config=SerpAPIConfig(api_key="x" * 24),
        config=HarnessConfig(write_outputs=False),
        one_credit=OneCreditConfig(write_outputs=False, scrape_top_k=1),
        organic_client=client,
        scraper=object(),
    )
    harness.scrape_top_k_per_stage = 1

    result = harness.run(
        ProductQuery(
            row_id="ROW-2",
            main_text="LEGO Classic 10698",
            country_code="IN",
            retailer_name=None,
            ean=None,
        ),
        return_trace=True,
    )

    assert result.state.budget.organic_used == 3
    assert result.state.task.country_code == "IN"
    assert [stage["name"] for stage in result.state.search_stage_trace] == [
        "manufacturer_primary",
        "country_alternative",
        "global_fallback",
    ]


def _schema() -> FeatureSchema:
    return FeatureSchema(
        schema_id="test",
        required_coverage_threshold=1.0,
        features=(
            FeatureDefinition(
                feature_id="brand",
                feature_name="Brand",
                criticality=FeatureCriticality.CRITICAL,
            ),
            FeatureDefinition(
                feature_id="scale",
                feature_name="Scale",
                criticality=FeatureCriticality.REQUIRED,
            ),
        ),
    )


def _assessment(url: str, *, complete: bool = True) -> URLFeatureAssessment:
    evidence = (
        FeatureEvidence(
            feature_id="brand",
            feature_name="Brand",
            source_url=url,
            value="Hot Wheels",
            status=FeatureEvidenceStatus.STRUCTURED_FOUND,
            confidence=0.99,
        ),
        FeatureEvidence(
            feature_id="scale",
            feature_name="Scale",
            source_url=url,
            value="1:64" if complete else None,
            status=(
                FeatureEvidenceStatus.STRUCTURED_FOUND
                if complete
                else FeatureEvidenceStatus.NOT_FOUND
            ),
            confidence=0.99 if complete else 0.0,
        ),
    )
    return URLFeatureAssessment(
        url=url,
        identity_accepted=True,
        identity_status="VERIFIED",
        source_role="PRIMARY_CANDIDATE",
        evidence=evidence,
        coverage=1.0 if complete else 0.5,
        required_coverage=1.0 if complete else 0.5,
        critical_coverage=1.0,
        missing_features=() if complete else ("scale",),
        conflicting_features=(),
    )


def _bundle(url: str, candidate_id: str = "CAND-001") -> BrowserEvidenceBundle:
    return BrowserEvidenceBundle(
        status=BrowserEvidenceStatus.COMPLETED,
        job_id="ROW-1",
        candidate_id=candidate_id,
        requested_url=url,
        final_url=url,
        browser_openable=True,
        rendered_product_verified=True,
        text_scrapable=True,
        gallery_discovered=True,
        direct_images_downloaded=1,
        screenshots_captured=1,
        multimodal_scrapable=True,
    )


def _verification(url: str) -> MatchVerification:
    return MatchVerification(
        url=url,
        identity_status="VERIFIED",
        ean_check="MATCHED",
        title_check="STRONG",
        quantity_check="MATCHED",
        brand_check="MATCHED",
        page_type_check="PRODUCT_DETAIL",
        title_match_score=1.0,
        exact_product_check="EXACT_MATCH",
        variant_check="MATCHED",
    )


def _scorecard(
    url: str,
    *,
    source_tier_marker: str,
    source_role_marker: str,
    scope_marker: str,
    confidence: float,
) -> CandidateScorecard:
    scrape = ScrapeResult(
        url=url,
        scraped=True,
        success=True,
        reachable=True,
        is_scrapable=True,
        status_code=200,
        final_url=url,
        title="Exact product",
        page_product_name="Exact product",
        looks_like_product_page=True,
        richness_score=0.9,
        word_count=500,
    )
    return CandidateScorecard(
        candidate=URLCandidate(
            url=url,
            title="Exact product",
            source_types=(
                source_tier_marker,
                source_role_marker,
                scope_marker,
            ),
        ),
        organic_score=1.0,
        ai_score=0.0,
        retailer_score=0.0,
        country_score=1.0,
        ean_score=1.0,
        title_score=1.0,
        product_page_score=1.0,
        scrape_score=1.0,
        identity_score=1.0,
        richness_score=0.9,
        weighted_confidence=confidence,
        confidence_cap=1.0,
        final_confidence=confidence,
        validation_status="VERIFIED",
        scrape=scrape,
        verification=_verification(url),
        retailer_check="NOT_PROVIDED",
        country_check="MATCHED",
    )


def test_strict_primary_acceptance_requires_browser_exact_features_and_durable_url() -> None:
    url = "https://shop.example.co/product/bmw-m3-wagon"
    decision = StrictPrimaryURLSelector().select(
        schema=_schema(),
        assessments=[_assessment(url)],
        browser_bundles=[_bundle(url)],
        scorecards=[],
    )

    assert decision.accepted is True
    assert decision.primary_url == url
    assert decision.browser_openable is True
    assert decision.text_scrapable is True
    assert decision.exact_product_verified is True
    assert decision.full_feature_coverage is True
    assert decision.durable_url is True


def test_strict_selector_prefers_qualified_manufacturer_and_retains_retailer() -> None:
    manufacturer = "https://www.hotwheels.com/product/bmw-m3-wagon"
    retailer = "https://retailer.example.co/product/bmw-m3-wagon"
    decision = StrictPrimaryURLSelector().select(
        schema=_schema(),
        assessments=[_assessment(manufacturer), _assessment(retailer)],
        browser_bundles=[
            _bundle(manufacturer, "CAND-001"),
            _bundle(retailer, "CAND-002"),
        ],
        scorecards=[
            _scorecard(
                manufacturer,
                source_tier_marker="source_tier_01_GLOBAL_MANUFACTURER",
                source_role_marker="source_role_MANUFACTURER",
                scope_marker="scope_manufacturer_primary",
                confidence=0.82,
            ),
            _scorecard(
                retailer,
                source_tier_marker="source_tier_04_MAJOR_COUNTRY_RETAILER",
                source_role_marker="source_role_MAJOR_COUNTRY_RETAILER",
                scope_marker="scope_country_alternative",
                confidence=0.99,
            ),
        ],
    )

    assert decision.accepted is True
    assert decision.primary_url == manufacturer
    assert decision.source_role == "MANUFACTURER"
    assert decision.manufacturer_url == manufacturer
    assert decision.retailer_url == retailer
    assert decision.selection_reason == "OFFICIAL_MANUFACTURER_PRIMARY_AFTER_STRICT_GATES"


def test_strict_selector_falls_back_to_retailer_when_manufacturer_is_incomplete() -> None:
    manufacturer = "https://www.hotwheels.com/product/bmw-m3-wagon"
    retailer = "https://retailer.example.co/product/bmw-m3-wagon"
    decision = StrictPrimaryURLSelector().select(
        schema=_schema(),
        assessments=[
            _assessment(manufacturer, complete=False),
            _assessment(retailer, complete=True),
        ],
        browser_bundles=[
            _bundle(manufacturer, "CAND-001"),
            _bundle(retailer, "CAND-002"),
        ],
        scorecards=[
            _scorecard(
                manufacturer,
                source_tier_marker="source_tier_01_GLOBAL_MANUFACTURER",
                source_role_marker="source_role_MANUFACTURER",
                scope_marker="scope_manufacturer_primary",
                confidence=0.99,
            ),
            _scorecard(
                retailer,
                source_tier_marker="source_tier_04_MAJOR_COUNTRY_RETAILER",
                source_role_marker="source_role_MAJOR_COUNTRY_RETAILER",
                scope_marker="scope_country_alternative",
                confidence=0.90,
            ),
        ],
    )

    assert decision.accepted is True
    assert decision.primary_url == retailer
    assert decision.source_role == "MAJOR_COUNTRY_RETAILER"
    assert decision.manufacturer_url is None
    assert decision.retailer_url == retailer
    assert decision.selection_reason == "RETAILER_PRIMARY_BECAUSE_NO_QUALIFIED_MANUFACTURER_PAGE"


def test_strict_primary_acceptance_returns_incomplete_page_for_review() -> None:
    url = "https://shop.example.co/product/bmw-m3-wagon"
    decision = StrictPrimaryURLSelector().select(
        schema=_schema(),
        assessments=[_assessment(url, complete=False)],
        browser_bundles=[_bundle(url)],
        scorecards=[],
    )

    assert decision.accepted is False
    assert decision.primary_url == url
    assert decision.browser_openable is True
    assert decision.text_scrapable is True
    assert decision.rendered_product_verified is True
    assert decision.exact_product_verified is True
    assert decision.full_feature_coverage is False
    assert decision.durable_url is True
    assert decision.selection_reason == "BEST_MEASURED_PRODUCT_URL_REQUIRES_REVIEW"
    assert decision.reasons == ("PRIMARY_URL_MISSING_REQUESTED_FEATURES",)


def test_durability_gate_rejects_ttl_or_signed_urls() -> None:
    gate = ProductURLDurabilityGate()

    assert gate.assess("https://shop.example/product/123?variant=blue").durable is True
    expiring = gate.assess(
        "https://shop.example/product/123?X-Amz-Expires=300&X-Amz-Signature=abc"
    )
    assert expiring.durable is False
    assert any(
        reason.startswith("URL_TRANSIENT_PARAMETER")
        for reason in expiring.reasons
    )
