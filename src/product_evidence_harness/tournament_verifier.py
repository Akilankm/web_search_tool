from __future__ import annotations

from src.product_evidence_harness.constants import PAGE_TYPE_NON_PRODUCT, PAGE_TYPE_PRODUCT_DETAIL
from src.product_evidence_harness.contracts import ScrapeResult
from src.product_evidence_harness.identity_verifier import ProductIdentityVerifier


class TournamentProductIdentityVerifier(ProductIdentityVerifier):
    """Tournament-safe identity verifier.

    A product-looking URL slug can be useful tournament evidence, but it must not
    be enough to call a scraped page an exact product match when the page body is
    thin, redirected, blocked, or only contains navigation/logo content.
    """

    min_thin_page_word_count: int = 80
    min_thin_page_richness: float = 0.30

    def _page_type(self, scrape: ScrapeResult) -> str:
        base = super()._page_type(scrape)
        if base != PAGE_TYPE_PRODUCT_DETAIL:
            return base
        if scrape.looks_like_product_page:
            return PAGE_TYPE_PRODUCT_DETAIL
        thin_or_generic = (
            (scrape.word_count or 0) < self.min_thin_page_word_count
            or (scrape.richness_score or 0.0) < self.min_thin_page_richness
        )
        product_name = (scrape.page_product_name or scrape.title or scrape.h1 or "").strip().lower()
        generic_names = {"mercado libre", "mercado libre logo image", "logo", "home", "homepage"}
        meaningful_name = bool(product_name and product_name not in generic_names and "logo image" not in product_name)
        has_product_evidence = bool(
            meaningful_name
            or scrape.has_price
            or scrape.structured_eans
            or scrape.specs
            or scrape.attributes
            or scrape.image_count > 1
        )
        if thin_or_generic and not has_product_evidence:
            return PAGE_TYPE_NON_PRODUCT
        return PAGE_TYPE_PRODUCT_DETAIL
