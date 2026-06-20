"""Query planning and AI Mode prompt constants."""

from __future__ import annotations

from typing import Final

# -----------------------------------------------------------------------------
# Query planning
# -----------------------------------------------------------------------------

ORGANIC_QUERY_MAX_CHARS: Final[int] = 450
AI_VALIDATION_QUERY_MAX_CHARS: Final[int] = 6500
AI_REPAIR_QUERY_MAX_CHARS: Final[int] = 6500

ORGANIC_PRODUCT_TERMS: Final[tuple[str, ...]] = (
    "product",
    "produkt",
    "toy",
    "toys",
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
    "REJECTED_CANDIDATES: <bullet list of rejected candidate number and reason>",
)

AI_REPAIR_TASK: Final[str] = (
    "The previous selected URL was rejected by deterministic validation. "
    "Re-evaluate the candidate list and return only a valid exact product detail URL. "
    "Return NO_MATCH if none are reliable."
)
