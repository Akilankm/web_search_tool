"""Ranker / confidence scoring constants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

TOKEN_REGEX: Final[str] = r"[a-zA-Z0-9À-ž]+"
MIN_TOKEN_LENGTH_FOR_TEXT_MATCH: Final[int] = 3

PRODUCT_PATH_KEYWORDS: Final[tuple[str, ...]] = (
    "product",
    "produkt",
    "p/",
    "shop",
    "item",
    "detail",
    "goods",
    "catalog",
    "toy",
    "toys",
    "hracky",
    "lego",
)

NON_PRODUCT_PATH_KEYWORDS: Final[tuple[str, ...]] = (
    "search",
    "category",
    "catalogsearch",
    "blog",
    "help",
    "support",
    "login",
    "cart",
    "basket",
    "wishlist",
    "privacy",
    "terms",
    "review",
    "reviews",
)

NEUTRAL_OPTIONAL_SIGNAL_SCORE: Final[float] = 0.5
WEAK_COUNTRY_SCORE: Final[float] = 0.2
PATH_COUNTRY_SCORE: Final[float] = 0.8
PERFECT_SCORE: Final[float] = 1.0
ZERO_SCORE: Final[float] = 0.0

AI_DECLARED_FINAL_SOURCE_SCORE: Final[float] = 0.12
ORGANIC_SOURCE_SCORE_POSITION_1: Final[float] = 0.10
ORGANIC_SOURCE_SCORE_POSITION_2_TO_5: Final[float] = 0.07
ORGANIC_SOURCE_SCORE_OTHER: Final[float] = 0.04
AI_REFERENCE_SOURCE_SCORE: Final[float] = 0.08
NON_REFERENCE_SOURCE_SCORE: Final[float] = 0.03

NON_PRODUCT_PENALTY: Final[float] = 0.30
NON_PRODUCT_SHAPE_SCORE: Final[float] = 0.15

EXACT_MATCH_CONFIDENCE_THRESHOLD: Final[float] = 0.82
HIGH_CONFIDENCE_THRESHOLD: Final[float] = 0.75
RETAILER_MATCH_THRESHOLD: Final[float] = 0.70
COUNTRY_MATCH_THRESHOLD: Final[float] = 0.70
PRODUCT_PAGE_MATCH_THRESHOLD: Final[float] = 0.50
STRONG_TEXT_MATCH_THRESHOLD: Final[float] = 0.60
PARTIAL_TEXT_MATCH_THRESHOLD: Final[float] = 0.30

PRODUCT_SHAPE_KEYWORD_SCORE: Final[float] = 0.40
PRODUCT_SHAPE_DEEP_PATH_SCORE: Final[float] = 0.25
PRODUCT_SHAPE_SLUG_SCORE: Final[float] = 0.20
PRODUCT_SHAPE_ID_SCORE: Final[float] = 0.15
MIN_PRODUCT_PATH_SEGMENTS: Final[int] = 2
SLUG_REGEX: Final[str] = r"[a-z0-9][-a-z0-9]{8,}"
ID_REGEX: Final[str] = r"\d{4,}"

CONFIDENCE_ROUND_DIGITS: Final[int] = 3

# Confidence caps prevent cosmetic confidence inflation.
CAP_RETAILER_MISMATCH: Final[float] = 0.40
# An alternative retailer (requested retailer not found, but the product is the
# correct one on another retailer) stays usable but is forced into the review
# band so it is never silently treated as the requested retailer.
CAP_RETAILER_ALTERNATIVE: Final[float] = 0.74
# An alternative country (requested country not found, but the product is correct
# on another country) stays usable but is forced into the review band.
CAP_COUNTRY_ALTERNATIVE: Final[float] = 0.74
# When global fallback is explicitly enabled, an out-of-country result is allowed
# to score highly but still carries a small honesty penalty vs an in-country one.
CAP_OUT_OF_COUNTRY: Final[float] = 0.85
# When country is locked (default) and only a weak in-country page exists, the
# pipeline still returns it but confidence is capped firmly into the review band
# with a strong explanatory reason.
CAP_FORCED_IN_COUNTRY_WEAK: Final[float] = 0.55
CAP_DEAD_URL: Final[float] = 0.35
CAP_NON_PRODUCT_PAGE: Final[float] = 0.55
CAP_EAN_NOT_VISIBLE_WHEN_REQUIRED: Final[float] = 0.82
CAP_NOT_IN_CANDIDATES_OR_REFERENCES: Final[float] = 0.65
# A candidate that was never scraped cannot outrank a verified scrapable page.
CAP_NOT_SCRAPED: Final[float] = 0.55
# A candidate that was scraped but yielded no usable content is almost rejected.
CAP_NOT_SCRAPABLE: Final[float] = 0.20

# Identity-driven caps. These are the hard guarantees that a returned URL is the
# CORRECT product, not merely a scrapable page.
CAP_IDENTITY_MISMATCH: Final[float] = 0.05      # different EAN / pack-size / variant
CAP_IDENTITY_UNVERIFIED: Final[float] = 0.25    # soft-404 / non-product / unconfirmable
CAP_IDENTITY_WEAK: Final[float] = 0.50          # only partial corroboration
CAP_IDENTITY_PROBABLE: Final[float] = 0.74      # strong but not EAN-proven -> needs review
# High confidence must be backed by hard justification, else capped here.
CAP_UNJUSTIFIED_HIGH_CONFIDENCE: Final[float] = 0.74
# EAN provided but the page neither confirms it nor exposes any structured EAN.
CAP_EAN_UNCONFIRMED_ON_PAGE: Final[float] = 0.74


@dataclass(frozen=True)
class ScoreWeights:
    organic_consensus: float = 0.10
    ai_evidence: float = 0.16
    retailer: float = 0.12
    country: float = 0.06
    ean: float = 0.14
    main_text: float = 0.12
    product_page_shape: float = 0.10
    scrape: float = 0.10
    identity: float = 0.30
    richness: float = 0.15  # High weight for product team: prioritizes rich extractable content
    toy_category: float = 0.0  # Gate-like: 0 for non_toy, 1.0 for toy_related, 0.5 for unknown


DEFAULT_SCORE_WEIGHTS: Final[ScoreWeights] = ScoreWeights()

SCORE_KEY_ORGANIC_CONSENSUS: Final[str] = "organic_consensus"
SCORE_KEY_AI_EVIDENCE: Final[str] = "ai_evidence"
SCORE_KEY_RETAILER: Final[str] = "retailer"
SCORE_KEY_COUNTRY: Final[str] = "country"
SCORE_KEY_EAN: Final[str] = "ean"
SCORE_KEY_MAIN_TEXT: Final[str] = "main_text"
SCORE_KEY_PRODUCT_PAGE_SHAPE: Final[str] = "product_page_shape"
SCORE_KEY_SOURCE_TYPE: Final[str] = "source_type"
SCORE_KEY_NON_PRODUCT_PENALTY: Final[str] = "non_product_penalty"
SCORE_KEY_SCRAPE: Final[str] = "scrape_verification"
SCORE_KEY_IDENTITY: Final[str] = "identity_verification"
SCORE_KEY_RICHNESS: Final[str] = "richness"
SCORE_KEY_TOY_CATEGORY: Final[str] = "toy_category"
