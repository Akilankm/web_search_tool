"""Tests for product-identity verification verdicts (identity_verifier.py)."""

from __future__ import annotations

from serp_hybrid_url_finder.constants import (
    IDENTITY_MISMATCH,
    IDENTITY_UNVERIFIED,
    IDENTITY_VERIFIED,
)
from serp_hybrid_url_finder.identity_verifier import ProductIdentityVerifier
from serp_hybrid_url_finder.models import ProductQuery, ScrapeResult


def _scrape(url="https://shop.example/p", **overrides) -> ScrapeResult:
    base = dict(
        url=url,
        scraped=True,
        success=True,
        reachable=True,
        is_scrapable=True,
        status_code=200,
        final_url=url,
    )
    base.update(overrides)
    return ScrapeResult(**base)


def test_matching_ean_is_verified():
    verifier = ProductIdentityVerifier()
    product = ProductQuery(
        main_text="Lego Star Wars X-Wing Starfighter",
        country_code="US",
        ean="4002051612345",
    )
    scrape = _scrape(
        page_product_name="Lego Star Wars X-Wing Starfighter",
        title="Lego Star Wars X-Wing Starfighter",
        structured_eans=("4002051612345",),
        verification_text="Lego Star Wars X-Wing Starfighter 4002051612345",
    )
    assert verifier.verify(product, scrape).identity_status == IDENTITY_VERIFIED


def test_conflicting_ean_is_mismatch():
    verifier = ProductIdentityVerifier()
    product = ProductQuery(
        main_text="Lego Star Wars X-Wing Starfighter",
        country_code="US",
        ean="4002051612345",
    )
    scrape = _scrape(
        page_product_name="Lego Star Wars X-Wing Starfighter",
        title="Lego Star Wars X-Wing Starfighter",
        structured_eans=("9999999999999",),  # page authoritatively declares a different GTIN
        verification_text="Lego Star Wars X-Wing Starfighter",
    )
    assert verifier.verify(product, scrape).identity_status == IDENTITY_MISMATCH


def test_pack_size_conflict_is_mismatch():
    verifier = ProductIdentityVerifier()
    product = ProductQuery(main_text="Acme Coffee Capsules 18 ks", country_code="CZ")
    scrape = _scrape(
        page_product_name="Acme Coffee Capsules 32 ks",  # 18 ks vs 32 ks
        title="Acme Coffee Capsules 32 ks",
        verification_text="Acme Coffee Capsules 32 ks",
    )
    assert verifier.verify(product, scrape).identity_status == IDENTITY_MISMATCH


def test_unscraped_page_is_unverified():
    verifier = ProductIdentityVerifier()
    product = ProductQuery(main_text="Anything", country_code="US")
    assert verifier.verify(product, None).identity_status == IDENTITY_UNVERIFIED
