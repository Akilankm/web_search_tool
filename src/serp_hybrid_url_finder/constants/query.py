"""Query planning and AI Mode prompt constants."""

from __future__ import annotations

from typing import Final

# -----------------------------------------------------------------------------
# Query planning
# -----------------------------------------------------------------------------

ORGANIC_QUERY_MAX_CHARS: Final[int] = 450
AI_VALIDATION_QUERY_MAX_CHARS: Final[int] = 6500
AI_REPAIR_QUERY_MAX_CHARS: Final[int] = 6500

# ---------------------------------------------------------------------------
# Language-aware purchase-intent verbs.
# Adding the local "buy" verb pushes Google toward commerce pages and away from
# editorial / review / Wikipedia results. These verbs appear on almost every
# retailer PDP ("jetzt kaufen", "acheter en ligne", "buy now").
# ---------------------------------------------------------------------------
ORGANIC_BUY_TERMS: Final[dict[str, str]] = {
    "de": "kaufen",
    "fr": "acheter",
    "it": "acquistare",
    "es": "comprar",
    "nl": "kopen",
    "pt": "comprar",
    "pl": "kup",
    "cs": "koupit",
    "sk": "kupit",
    "hu": "venni",
    "ro": "cumpara",
    "en": "buy",
    "ja": "購入",
    "zh": "购买",
}

# ---------------------------------------------------------------------------
# Language-aware PDP URL path hints for the inurl: operator.
# inurl:produkt matches /produkt/slug, /de/produkt/..., ?produkt=... etc.
# First entry is used (most language-native); fallback to "_default".
# ---------------------------------------------------------------------------
ORGANIC_INURL_PDP_HINTS: Final[dict[str, tuple[str, ...]]] = {
    "de": ("produkt", "artikel", "product"),
    "fr": ("produit", "article", "product"),
    "it": ("prodotto", "articolo", "product"),
    "nl": ("product", "artikel"),
    "es": ("producto", "articulo", "product"),
    "pt": ("produto", "artigo", "product"),
    "pl": ("produkt", "product"),
    "cs": ("produkt", "product"),
    "sk": ("produkt", "product"),
    "hu": ("termek", "product"),
    "en": ("product", "item"),
    "_default": ("product", "produkt"),
}

# ---------------------------------------------------------------------------
# Editorial / social sites to soft-exclude.
# Kept deliberately SHORT — every extra exclusion costs recall on long-tail
# products. Only definitive non-retailers included.
# ---------------------------------------------------------------------------
ORGANIC_EDITORIAL_EXCLUSIONS: Final[tuple[str, ...]] = (
    "-site:youtube.com",
    "-site:reddit.com",
    "-site:wikipedia.org",
    "-site:facebook.com",
    "-site:instagram.com",
    "-filetype:pdf",
)

# ---------------------------------------------------------------------------
# Legacy constants — kept for backward compatibility only.
# New query builders use ORGANIC_BUY_TERMS / ORGANIC_INURL_PDP_HINTS /
# ORGANIC_EDITORIAL_EXCLUSIONS instead.
# ---------------------------------------------------------------------------
ORGANIC_PRODUCT_TERMS: Final[tuple[str, ...]] = (
    "product",
    "produkt",
)

ORGANIC_DETAIL_TERMS: Final[tuple[str, ...]] = (
    "product detail",
    "official product page",
    "retailer product page",
)

ORGANIC_NOISE_EXCLUSIONS: Final[tuple[str, ...]] = (
    "-review",
    "-reviews",
    "-youtube",
    "-facebook",
    "-instagram",
    "-tiktok",
    "-pinterest",
    "-pdf",
    "-manual",
    "-catalogue",
    "-catalog",
    "-image",
    "-images",
    "-blog",
    "-forum",
    "-login",
    "-cart",
    "-basket",
    "-wishlist",
)

QUERY_SITE_OPERATOR: Final[str] = "site:{domain}"


# -----------------------------------------------------------------------------
# AI Mode validation prompt
# -----------------------------------------------------------------------------

AI_VALIDATOR_ROLE: Final[str] = (
    "You are validating product URL candidates using indexed web evidence."
)

AI_VALIDATOR_TASK: Final[str] = (
    "Choose the single best exact product detail URL from the candidate list. "
    "Use evidence, not guesses. Do not invent a URL. "
    "Do not return a URL outside the candidates unless it appears in your cited references."
)

AI_VALIDATOR_RULES: Final[tuple[str, ...]] = (
    "Prefer EAN/GTIN/barcode match over fuzzy title match.",
    "If retailer_name is provided, prefer that retailer's product detail page.",
    "The final URL must be a single product detail page.",
    "Reject homepage, brand homepage, category, search, listing, review, social, image, PDF, cart, help, blog, or forum pages.",
    "Reject different product variants, bundles, sizes, colors, or unrelated toys.",
    "Pack size / quantity must match EXACTLY: e.g. '18 KS' (18 pieces) must NOT be matched to '32 KS' (32 pieces). A different count is a different product.",
    "Reject soft-404 or 'product not found' pages even if they load.",
    "PRODUCT CATEGORY: The final URL must be for a toy/game/collectible product. Reject books, textbooks, stationery, office supplies, or non-toy items.",
    "If none are reliable, return NO_MATCH.",
    "Provide concrete justification and rejection reasons.",
)

AI_VALIDATOR_OUTPUT_CONTRACT: Final[tuple[str, ...]] = (
    "FINAL_URL: <one URL from candidates or cited references, or NO_MATCH>",
    "MATCH_DECISION: <EXACT | HIGH | MEDIUM | LOW | NO_MATCH>",
    "CONFIDENCE_REASON: <short reason>",
    "EAN_EVIDENCE: <matched | not_visible | not_provided>",
    "TITLE_EVIDENCE: <matched | partial | weak>",
    "RETAILER_EVIDENCE: <matched | weak | not_provided>",
    "COUNTRY_EVIDENCE: <matched | weak | not_provided>",
    "PRODUCT_PAGE_EVIDENCE: <product_detail | category | search | homepage | listing | unknown>",
    "TOY_CATEGORY_EVIDENCE: <toy_related | non_toy | unknown>",
    "REJECTED_CANDIDATES: <bullet list of rejected candidate number and reason>",
)

AI_REPAIR_TASK: Final[str] = (
    "The previous selected URL was rejected by deterministic validation. "
    "Re-evaluate the candidate list and return only a valid exact product detail URL. "
    "Return NO_MATCH if none are reliable."
)
