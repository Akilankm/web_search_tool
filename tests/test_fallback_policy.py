"""Tests for country-locked, fallback-aware final selection (pipeline._select_final)."""

from __future__ import annotations

from serp_hybrid_url_finder.config import PipelineConfig, SerpAPIConfig
from serp_hybrid_url_finder.constants import (
    COUNTRY_CHECK_ALTERNATIVE,
    COUNTRY_CHECK_MATCHED,
    IDENTITY_VERIFIED,
)
from serp_hybrid_url_finder.models import (
    MatchVerification,
    ScoredURLCandidate,
    ScrapeResult,
    URLCandidate,
)
from serp_hybrid_url_finder.pipeline import HybridProductURLFinderPipeline


def _pipeline(**cfg) -> HybridProductURLFinderPipeline:
    # Stub the network clients and scraper so construction never touches the
    # network; only the pure selection logic is exercised.
    return HybridProductURLFinderPipeline(
        serp_config=SerpAPIConfig(api_key="test-key"),
        pipeline_config=PipelineConfig(**cfg),
        organic_client=object(),
        ai_client=object(),
        scraper=object(),
    )


def _scored(url, *, country_check, scrapable=True, richness=0.5, confidence=0.8):
    scrape = ScrapeResult(
        url=url, scraped=True, success=True, reachable=True,
        is_scrapable=scrapable, status_code=200, final_url=url, richness_score=richness,
    )
    verification = MatchVerification(
        url=url, identity_status=IDENTITY_VERIFIED, ean_check="MATCHED",
        title_check="STRONG", quantity_check="MATCHED", brand_check="MATCHED",
        page_type_check="UNKNOWN", title_match_score=1.0,
    )
    return ScoredURLCandidate(
        candidate=URLCandidate(url=url), confidence=confidence,
        is_exact_product_match=True, reason="", score_breakdown={},
        scrape=scrape, verification=verification, country_check=country_check,
    )


def test_locked_prefers_in_country_over_richer_out_of_country():
    pipe = _pipeline(allow_global_fallback=False)
    out_rich = _scored("https://out", country_check=COUNTRY_CHECK_ALTERNATIVE, richness=0.9)
    in_thin = _scored("https://in", country_check=COUNTRY_CHECK_MATCHED, richness=0.2)
    final = pipe._select_final([out_rich, in_thin])
    assert final is not None
    assert final.candidate.url == "https://in"


def test_locked_returns_none_when_only_out_of_country():
    pipe = _pipeline(allow_global_fallback=False)
    out_only = _scored("https://out", country_check=COUNTRY_CHECK_ALTERNATIVE)
    assert pipe._select_final([out_only]) is None


def test_global_fallback_accepts_out_of_country():
    pipe = _pipeline(allow_global_fallback=True)
    out_only = _scored("https://out", country_check=COUNTRY_CHECK_ALTERNATIVE)
    final = pipe._select_final([out_only])
    assert final is not None
    assert final.candidate.url == "https://out"


def test_non_scrapable_in_country_is_rejected_when_locked():
    pipe = _pipeline(allow_global_fallback=False)
    in_dead = _scored("https://in", country_check=COUNTRY_CHECK_MATCHED, scrapable=False)
    assert pipe._select_final([in_dead]) is None


def test_has_out_of_country_alternative_detection():
    pipe = _pipeline()
    out_alt = _scored("https://out", country_check=COUNTRY_CHECK_ALTERNATIVE)
    in_match = _scored("https://in", country_check=COUNTRY_CHECK_MATCHED)
    assert pipe._has_out_of_country_alternative([out_alt]) is True
    assert pipe._has_out_of_country_alternative([in_match]) is False
