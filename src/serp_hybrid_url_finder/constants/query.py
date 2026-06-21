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
    "Choose the single best product detail URL for the requested product from the "
    "candidate list. Use evidence, not guesses. Do not invent a URL. Do not return a "
    "URL outside the candidates unless it appears in your cited references. "
    "Always prefer returning the closest matching product detail page over NO_MATCH: "
    "return NO_MATCH ONLY when not a single candidate could plausibly be the requested "
    "product. If you are not fully certain, still return your single closest candidate "
    "and lower MATCH_DECISION (HIGH / MEDIUM / LOW) to reflect that uncertainty. "
    "A page being slow, bot-protected, or JavaScript-heavy does NOT disqualify it: "
    "judge each candidate using Google's indexed knowledge of that page (title, "
    "breadcrumbs, structured data, snippet), not whether it loads for you."
)

AI_VALIDATOR_RULES: Final[tuple[str, ...]] = (
    "Prefer EAN/GTIN/barcode match over fuzzy title match.",
    "If retailer_name is provided, prefer that retailer's product detail page.",
    "The final URL must be a single product detail page. Never select a homepage, "
    "brand homepage, category, search, listing, review, social, image, PDF, cart, "
    "help, blog, or forum page.",
    "If candidates differ by variant, bundle, size, colour, or pack/quantity (e.g. "
    "'18 KS' = 18 pieces is a DIFFERENT product from '32 KS' = 32 pieces), select the "
    "one that matches the requested product EXACTLY. If only a near-variant exists, "
    "return it as the closest match, lower MATCH_DECISION to LOW, and state the exact "
    "difference in CONFIDENCE_REASON.",
    "Never select a soft-404 or 'product not found' page.",
    "PRODUCT CATEGORY: prefer a toy / game / collectible product page. Treat books, "
    "textbooks, stationery, office supplies, or other non-toy items as a poor match - "
    "select one only if it is genuinely the requested product, and set "
    "TOY_CATEGORY_EVIDENCE accordingly.",
    "A page being slow, bot-protected, or JavaScript-heavy is NOT a reason to reject "
    "it; judge each candidate from Google's indexed knowledge of the page.",
    "Always return your single closest product detail candidate. Return NO_MATCH ONLY "
    "when NOT ONE candidate could plausibly be the requested product.",
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
    "Re-evaluate the candidate list and return the single closest valid product detail "
    "URL for the requested product, lowering MATCH_DECISION to reflect any remaining "
    "uncertainty. Return NO_MATCH ONLY if not one candidate could plausibly be the "
    "requested product."
)
