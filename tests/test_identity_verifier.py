from __future__ import annotations

from product_evidence_harness.constants import IDENTITY_MISMATCH, IDENTITY_UNVERIFIED, IDENTITY_VERIFIED
from product_evidence_harness.contracts import ProductQuery, ScrapeResult
from product_evidence_harness.identity_verifier import ProductIdentityVerifier


def _scrape(url="https://shop.example/p", **overrides) -> ScrapeResult:
    base = dict(
        url=url,
        scraped=True,
        success=True,
        reachable=True,
        is_scrapable=True,
        status_code=200,
        final_url=url,
        looks_like_product_page=True,
    )
    base.update(overrides)
    return ScrapeResult(**base)


def test_matching_ean_is_verified():
    verifier = ProductIdentityVerifier()
    product = ProductQuery(main_text="Lego Star Wars X-Wing Starfighter", country_code="US", ean="4002051612345")
    scrape = _scrape(
        page_product_name="Lego Star Wars X-Wing Starfighter",
        title="Lego Star Wars X-Wing Starfighter",
        structured_eans=("4002051612345",),
        verification_text="Lego Star Wars X-Wing Starfighter 4002051612345",
    )
    assert verifier.verify(product, scrape).identity_status == IDENTITY_VERIFIED


def test_conflicting_ean_with_exact_text_is_warning_not_mismatch():
    verifier = ProductIdentityVerifier()
    product = ProductQuery(main_text="Pokemon Mega Entwicklung Wachsendes Chaos Booster DE", country_code="CH", ean="0196214141070")
    scrape = _scrape(
        page_product_name="Pokemon Mega Entwicklung Wachsendes Chaos Booster DE",
        title="Pokemon Mega Entwicklung Wachsendes Chaos Booster DE",
        structured_eans=("0196214141087",),
        verification_text="EAN: 0196214141087 Pokemon Mega Entwicklung Wachsendes Chaos Booster DE",
    )
    verification = verifier.verify(product, scrape)
    assert verification.identity_status == IDENTITY_VERIFIED
    assert verification.ean_check == "CONFLICT"
    assert verification.ean_conflict_is_blocking is False


def test_sibling_variant_is_mismatch_even_with_high_title_overlap():
    verifier = ProductIdentityVerifier()
    product = ProductQuery(main_text="Pokemon Mega Entwicklung Wachsendes Chaos Booster DE", country_code="CH", ean="0196214141070")
    scrape = _scrape(
        page_product_name="Pokemon Mega Entwicklung Wachsendes Chaos Booster Display DE",
        title="Pokemon Mega Entwicklung Wachsendes Chaos Booster Display DE",
        structured_eans=("0196214141087",),
        verification_text="EAN: 0196214141087 Pokemon Mega Entwicklung Wachsendes Chaos Booster Display DE",
    )
    verification = verifier.verify(product, scrape)
    assert verification.identity_status == IDENTITY_MISMATCH
    assert verification.variant_check == "CONFLICT"


def test_pack_size_conflict_is_mismatch_by_default():
    verifier = ProductIdentityVerifier()
    product = ProductQuery(main_text="Acme Coffee Capsules 18 ks", country_code="CZ")
    scrape = _scrape(
        page_product_name="Acme Coffee Capsules 32 ks",
        title="Acme Coffee Capsules 32 ks",
        verification_text="Acme Coffee Capsules 32 ks",
    )
    assert verifier.verify(product, scrape).identity_status == IDENTITY_MISMATCH


def test_unscraped_page_is_unverified():
    verifier = ProductIdentityVerifier()
    product = ProductQuery(main_text="Anything", country_code="US")
    assert verifier.verify(product, None).identity_status == IDENTITY_UNVERIFIED
