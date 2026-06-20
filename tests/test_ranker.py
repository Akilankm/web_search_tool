"""Tests for the richness/country-aware ranking order (ranker._sort_key)."""

from __future__ import annotations

from serp_hybrid_url_finder.constants import (
    COUNTRY_CHECK_ALTERNATIVE,
    COUNTRY_CHECK_MATCHED,
    IDENTITY_PROBABLE,
    IDENTITY_VERIFIED,
)
from serp_hybrid_url_finder.models import (
    MatchVerification,
    ScoredURLCandidate,
    ScrapeResult,
    URLCandidate,
)
from serp_hybrid_url_finder.ranker import ProductURLRanker


def _make_scored(url, *, identity, country_check, richness, confidence, scrapable=True):
    scrape = ScrapeResult(
        url=url,
        scraped=True,
        success=True,
        reachable=True,
        is_scrapable=scrapable,
        status_code=200,
        final_url=url,
        richness_score=richness,
    )
    verification = MatchVerification(
        url=url,
        identity_status=identity,
        ean_check="MATCHED",
        title_check="STRONG",
        quantity_check="MATCHED",
        brand_check="MATCHED",
        page_type_check="UNKNOWN",
        title_match_score=1.0,
    )
    return ScoredURLCandidate(
        candidate=URLCandidate(url=url),
        confidence=confidence,
        is_exact_product_match=True,
        reason="",
        score_breakdown={},
        scrape=scrape,
        verification=verification,
        country_check=country_check,
    )


def _ordered_urls(ranker, items):
    return [c.candidate.url for c in sorted(items, key=ranker._sort_key, reverse=True)]


def test_correct_identity_outranks_richer_but_weaker_identity():
    ranker = ProductURLRanker()
    verified = _make_scored(
        "https://a", identity=IDENTITY_VERIFIED,
        country_check=COUNTRY_CHECK_MATCHED, richness=0.1, confidence=0.5,
    )
    probable = _make_scored(
        "https://b", identity=IDENTITY_PROBABLE,
        country_check=COUNTRY_CHECK_MATCHED, richness=0.9, confidence=0.9,
    )
    assert _ordered_urls(ranker, [probable, verified])[0] == "https://a"


def test_in_country_outranks_richer_out_of_country():
    ranker = ProductURLRanker()
    in_country = _make_scored(
        "https://in", identity=IDENTITY_VERIFIED,
        country_check=COUNTRY_CHECK_MATCHED, richness=0.1, confidence=0.5,
    )
    out_country = _make_scored(
        "https://out", identity=IDENTITY_VERIFIED,
        country_check=COUNTRY_CHECK_ALTERNATIVE, richness=0.9, confidence=0.9,
    )
    assert _ordered_urls(ranker, [out_country, in_country])[0] == "https://in"


def test_richness_breaks_tie_before_confidence():
    ranker = ProductURLRanker()
    richer = _make_scored(
        "https://rich", identity=IDENTITY_VERIFIED,
        country_check=COUNTRY_CHECK_MATCHED, richness=0.9, confidence=0.5,
    )
    confident = _make_scored(
        "https://conf", identity=IDENTITY_VERIFIED,
        country_check=COUNTRY_CHECK_MATCHED, richness=0.3, confidence=0.9,
    )
    assert _ordered_urls(ranker, [confident, richer])[0] == "https://rich"
