"""Product identity verification constants.

Scrapability only proves a page LOADS with content. Identity verification proves
the scraped page is genuinely THE requested product (same EAN, same distinctive
title, same pack-size / variant) and not a different variant (e.g. 18 KS vs
32 KS), a similar-but-wrong product, or a soft-404 "not found" page that still
returns HTTP 200 with content.

Market/language-specific heuristics (quantity units, currency terms, soft-404
phrases, stopwords) live in ``serp_hybrid_url_finder.markets`` and are no longer
hardcoded here.
"""

from __future__ import annotations

from typing import Final

REQUIRE_IDENTITY_VERIFIED_DEFAULT: Final[bool] = True
ALLOW_PROBABLE_AS_FINAL_DEFAULT: Final[bool] = True
HIGH_CONFIDENCE_REQUIRES_JUSTIFICATION_DEFAULT: Final[bool] = True

# Country is the top-priority, mandatory input. By default the requested country
# is a HARD scope: the pipeline returns the best in-country product URL (capped
# and flagged when weak) and never silently substitutes another country. Set
# ``allow_global_fallback=True`` on the config to permit an out-of-country URL
# when nothing suitable exists in-country.
ALLOW_GLOBAL_FALLBACK_DEFAULT: Final[bool] = False

# Identity verdict for a single scraped candidate.
IDENTITY_VERIFIED: Final[str] = "VERIFIED"      # hard proof (EAN) or strong corroboration
IDENTITY_PROBABLE: Final[str] = "PROBABLE"      # strong title + real PDP, EAN not confirmed
IDENTITY_WEAK: Final[str] = "WEAK"              # partial signals only
IDENTITY_MISMATCH: Final[str] = "MISMATCH"      # conflicting identity (different EAN / quantity)
IDENTITY_UNVERIFIED: Final[str] = "UNVERIFIED"  # soft-404 / non-product / no usable content

IDENTITY_RANK_ORDER: Final[dict[str, int]] = {
    IDENTITY_VERIFIED: 4,
    IDENTITY_PROBABLE: 3,
    IDENTITY_WEAK: 2,
    IDENTITY_UNVERIFIED: 1,
    IDENTITY_MISMATCH: 0,
}

IDENTITY_SCORE_MAP: Final[dict[str, float]] = {
    IDENTITY_VERIFIED: 1.00,
    IDENTITY_PROBABLE: 0.75,
    IDENTITY_WEAK: 0.45,
    IDENTITY_UNVERIFIED: 0.15,
    IDENTITY_MISMATCH: 0.00,
}

# Sub-check outcomes.
CHECK_EAN_MATCHED: Final[str] = "MATCHED"
CHECK_EAN_CONFLICT: Final[str] = "CONFLICT"
CHECK_EAN_ABSENT: Final[str] = "ABSENT"
CHECK_NOT_PROVIDED: Final[str] = "NOT_PROVIDED"

CHECK_TITLE_STRONG: Final[str] = "STRONG"
CHECK_TITLE_PARTIAL: Final[str] = "PARTIAL"
CHECK_TITLE_WEAK: Final[str] = "WEAK"

CHECK_QTY_MATCHED: Final[str] = "MATCHED"
CHECK_QTY_CONFLICT: Final[str] = "CONFLICT"
CHECK_QTY_UNKNOWN: Final[str] = "UNKNOWN"
CHECK_QTY_NOT_APPLICABLE: Final[str] = "NOT_APPLICABLE"

CHECK_BRAND_MATCHED: Final[str] = "MATCHED"
CHECK_BRAND_ABSENT: Final[str] = "ABSENT"
CHECK_BRAND_NOT_APPLICABLE: Final[str] = "NOT_APPLICABLE"

# Retailer match outcome for the returned URL.
RETAILER_CHECK_MATCHED: Final[str] = "MATCHED"            # requested retailer
RETAILER_CHECK_ALTERNATIVE: Final[str] = "ALTERNATIVE"    # different retailer (fallback)
RETAILER_CHECK_NOT_PROVIDED: Final[str] = "NOT_PROVIDED"  # no retailer requested

# Country match outcome for the returned URL.
COUNTRY_CHECK_MATCHED: Final[str] = "MATCHED"            # requested country
COUNTRY_CHECK_ALTERNATIVE: Final[str] = "ALTERNATIVE"    # different country (fallback)
COUNTRY_CHECK_NOT_PROVIDED: Final[str] = "NOT_PROVIDED"  # no country requested

PAGE_TYPE_SOFT_404: Final[str] = "SOFT_404"
PAGE_TYPE_NON_PRODUCT: Final[str] = "NON_PRODUCT"
PAGE_TYPE_UNKNOWN: Final[str] = "UNKNOWN"

# Final per-row validation status used for downstream submission.
VALIDATION_VERIFIED: Final[str] = "VERIFIED"          # safe to submit
VALIDATION_NEEDS_REVIEW: Final[str] = "NEEDS_REVIEW"  # human review recommended
VALIDATION_REJECTED: Final[str] = "REJECTED"          # identity conflict / unverifiable
VALIDATION_NO_MATCH: Final[str] = "NO_MATCH"          # nothing found

# Title token matching thresholds (distinctive tokens only).
# 0.60: 2/3 tokens qualify as STRONG (was 0.70 which needed 3/3 for short names
# like 'PLÜSCH HUND BRAUN' and returned PARTIAL → WEAK → rejected).
TITLE_STRONG_MATCH_THRESHOLD: Final[float] = 0.60
TITLE_PARTIAL_MATCH_THRESHOLD: Final[float] = 0.40

# JSON-LD structured-data keys used for authoritative identity.
JSONLD_EAN_KEYS: Final[tuple[str, ...]] = (
    "gtin13", "gtin12", "gtin14", "gtin8", "gtin", "ean", "barcode", "mpn",
)
JSONLD_PRODUCT_TYPE_HINTS: Final[tuple[str, ...]] = ("product", "offer")

VERIFICATION_TEXT_MAX_CHARS: Final[int] = 12000
EAN_DIGIT_LENGTHS: Final[tuple[int, ...]] = (13, 14, 12, 8)
