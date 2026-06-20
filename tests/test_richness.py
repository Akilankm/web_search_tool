"""Tests for the information-richness scoring (scraper + richness constants)."""

from __future__ import annotations

import pytest

from serp_hybrid_url_finder.constants import RICHNESS_FIELD_WEIGHTS
from serp_hybrid_url_finder.scraper import CrawlScraper


def test_richness_field_weights_sum_to_one():
    assert sum(RICHNESS_FIELD_WEIGHTS.values()) == pytest.approx(1.0)


def _score(**overrides) -> float:
    base = dict(
        specs={},
        attributes={},
        brand="",
        manufacturer="",
        structured_eans=(),
        description="",
        has_price=False,
        image_urls=(),
        image_count=0,
        availability="",
        page_product_name="",
    )
    base.update(overrides)
    return CrawlScraper._compute_richness_score(**base)


def test_empty_page_has_zero_richness():
    assert _score() == 0.0


def test_fully_populated_page_reaches_full_richness():
    score = _score(
        specs={f"k{i}": f"v{i}" for i in range(6)},
        brand="Acme",
        manufacturer="Acme Corp",
        structured_eans=("4002051612345",),
        description="x" * 200,
        has_price=True,
        image_urls=("u1", "u2", "u3"),
        image_count=3,
        availability="in stock",
        page_product_name="Acme Widget",
    )
    assert score == pytest.approx(1.0)


def test_richer_page_scores_strictly_higher():
    sparse = _score(brand="Acme")
    rich = _score(brand="Acme", has_price=True, description="x" * 200)
    assert 0.0 < sparse < rich < 1.0
