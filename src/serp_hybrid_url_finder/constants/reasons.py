"""Match reason text constants."""

from __future__ import annotations

from typing import Final

REASON_EAN_MATCHED: Final[str] = "EAN matched"
REASON_EAN_NOT_VISIBLE: Final[str] = "EAN not visible in evidence"
REASON_RETAILER_MATCHED: Final[str] = "retailer/domain matched"
REASON_RETAILER_WEAK: Final[str] = "retailer/domain weak or missing"
REASON_COUNTRY_MATCHED: Final[str] = "country signal matched"
REASON_COUNTRY_WEAK: Final[str] = "country signal weak or missing"
REASON_MAIN_TEXT_STRONG: Final[str] = "main text tokens strongly matched"
REASON_MAIN_TEXT_PARTIAL: Final[str] = "main text tokens partially matched"
REASON_MAIN_TEXT_WEAK: Final[str] = "main text token match is weak"
REASON_PRODUCT_PAGE_SHAPE_MATCHED: Final[str] = "URL shape looks like product page"
REASON_PRODUCT_PAGE_SHAPE_WEAK: Final[str] = "URL shape is not strongly product-page-like"
REASON_SCRAPABLE: Final[str] = "verified scrapable via crawl4ai"
REASON_NOT_SCRAPABLE: Final[str] = "crawl4ai could not scrape usable content"
REASON_NOT_SCRAPED: Final[str] = "not scraped with crawl4ai"
REASON_NO_URL_EXTRACTED: Final[str] = "No usable URL candidate was found."
REASON_AI_NO_MATCH: Final[str] = "AI Mode returned NO_MATCH."
REASON_NO_SCRAPABLE_URL: Final[str] = "No candidate URL was verified scrapable by crawl4ai."
REASON_NO_VERIFIED_URL: Final[str] = (
    "No candidate URL passed product-identity verification on its scraped content."
)
REASON_IDENTITY_MISMATCH: Final[str] = "scraped page is a different product / variant"
REASON_RETAILER_ALTERNATIVE: Final[str] = (
    "requested retailer not found with this product; returned a verified ALTERNATIVE retailer"
)
REASON_NO_REQUESTED_RETAILER_URL: Final[str] = (
    "Requested retailer was required but no verified URL was found on that retailer."
)

# Country-scope / richness-aware selection reasons.
REASON_FORCED_IN_COUNTRY_WEAK: Final[str] = (
    "Country is locked to the requested market and only a weak / sparsely scrapable "
    "in-country product page exists; returned it with reduced confidence rather than "
    "substituting another country. Enable allow_global_fallback to widen the search."
)
REASON_OUT_OF_COUNTRY_FALLBACK: Final[str] = (
    "No suitable in-country product page was found; global fallback is enabled, so a "
    "verified out-of-country product URL was returned with a small honesty penalty."
)
REASON_RICHEST_AMONG_VERIFIED: Final[str] = (
    "selected the richest scrapable product page among the correct, in-scope candidates"
)
