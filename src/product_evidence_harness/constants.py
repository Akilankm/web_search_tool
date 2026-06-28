from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Status vocabulary
# ---------------------------------------------------------------------------

VALIDATION_VERIFIED = "VERIFIED"
VALIDATION_NEEDS_REVIEW = "NEEDS_REVIEW"
VALIDATION_REJECTED = "REJECTED"
VALIDATION_NO_MATCH = "NO_MATCH"
VALIDATION_UNRESOLVED = "UNRESOLVED"

IDENTITY_VERIFIED = "VERIFIED"
IDENTITY_PROBABLE = "PROBABLE"
IDENTITY_WEAK = "WEAK"
IDENTITY_MISMATCH = "MISMATCH"
IDENTITY_UNVERIFIED = "UNVERIFIED"

CHECK_MATCHED = "MATCHED"
CHECK_CONFLICT = "CONFLICT"
CHECK_ABSENT = "ABSENT"
CHECK_NOT_PROVIDED = "NOT_PROVIDED"
CHECK_UNKNOWN = "UNKNOWN"
CHECK_STRONG = "STRONG"
CHECK_PARTIAL = "PARTIAL"
CHECK_WEAK = "WEAK"
CHECK_NOT_APPLICABLE = "NOT_APPLICABLE"

PAGE_TYPE_PRODUCT_DETAIL = "PRODUCT_DETAIL"
PAGE_TYPE_LISTING = "LISTING"
PAGE_TYPE_SOFT_404 = "SOFT_404"
PAGE_TYPE_NON_PRODUCT = "NON_PRODUCT"
PAGE_TYPE_UNKNOWN = "UNKNOWN"

COUNTRY_MATCHED = "MATCHED"
COUNTRY_ALTERNATIVE = "ALTERNATIVE"
COUNTRY_NOT_PROVIDED = "NOT_PROVIDED"

RETAILER_MATCHED = "MATCHED"
RETAILER_ALTERNATIVE = "ALTERNATIVE"
RETAILER_NOT_PROVIDED = "NOT_PROVIDED"

DISCOVERY_MODE_STRICT = "strict_product_url"
DISCOVERY_MODE_EVIDENCE = "product_evidence"

# ---------------------------------------------------------------------------
# Action vocabulary
# ---------------------------------------------------------------------------

ACTION_ORGANIC_SEARCH = "organic_search"
ACTION_AI_MODE_SEARCH = "ai_mode_search"
ACTION_SCRAPE_URL = "scrape_url"
ACTION_FINISH = "finish"

TERMINATION_VERIFIED = "verified_primary_found"
TERMINATION_BUDGET_EXHAUSTED = "budget_exhausted"
TERMINATION_NO_MORE_ACTIONS = "no_more_actions"
TERMINATION_MAX_ITERATIONS = "max_iterations"
TERMINATION_NEEDS_REVIEW = "needs_review"

# ---------------------------------------------------------------------------
# SerpAPI
# ---------------------------------------------------------------------------

SERPAPI_SEARCH_URL = "https://serpapi.com/search.json"
SERPAPI_API_KEY_ENV = "SERPAPI_API_KEY"
SERPAPI_ENGINE_GOOGLE = "google"
SERPAPI_ENGINE_GOOGLE_AI_MODE = "google_ai_mode"
SERPAPI_OUTPUT_JSON = "json"

# ---------------------------------------------------------------------------
# URL / extraction heuristics
# ---------------------------------------------------------------------------

URL_REGEX = r"https?://[^\s<>)\]}'\"]+"
VALID_URL_SCHEMES = {"http", "https"}
BLOCKED_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "pinterest.",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "linkedin.com",
    "reddit.com",
    "wikipedia.org",
)
BLOCKED_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip",
)

TITLE_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "into", "this", "that",
    "toy", "toys", "figure", "figurka", "set", "pack", "pcs", "piece", "pieces",
    "kusu", "kusů", "ks", "stk", "stück", "stuck", "szt", "piezas", "pieza",
    "para", "con", "los", "las", "una", "del", "von", "der", "die", "das", "und", "mit",
})
TOKEN_REGEX = r"[a-zA-Z0-9À-ž]+"
EAN_REGEX = r"\b\d{8,14}\b"
QUANTITY_REGEX = r"(\d{1,4})\s*[-]?\s*(pcs?|pieces?|packs?|count|ct|ks|kusu|kusů|stk|stück|stuck|szt|unidades|unidad|uds|und|piezas|pieza|pzas|pza)\b"

SOFT_404_PHRASES = (
    "page not found", "product not found", "not found", "no longer available",
    "no products found", "no results", "stránka nenalezena", "stranka nenalezena",
    "produkt nenalezen", "seite nicht gefunden", "página no encontrada",
    "pagina no encontrada", "producto no encontrado", "no disponible",
)
ADD_TO_CART_PHRASES = (
    "add to cart", "add to basket", "buy now", "do košíku", "do kosiku",
    "koupit", "in den warenkorb", "do koszyka", "kosárba", "comprar",
    "agregar al carrito", "añadir al carrito",
)
PRODUCT_URL_HINTS = (
    "/product", "/produkt", "/prodotti", "/p/", "/dp/", "/item", "/shop/", "/sku/",
)
LISTING_URL_HINTS = (
    "/category", "/categorie", "/kategorie", "/collection", "/collections",
    "/search", "/catalog", "/browse", "/filter",
)


# ---------------------------------------------------------------------------
# Exact-product / variant heuristics
# ---------------------------------------------------------------------------

EXACT_PRODUCT_MATCH = "EXACT_MATCH"
EXACT_PRODUCT_WEAK = "WEAK_MATCH"
EXACT_PRODUCT_MISMATCH = "MISMATCH"

VARIANT_MATCH = "MATCHED"
VARIANT_CONFLICT = "CONFLICT"
VARIANT_UNKNOWN = "UNKNOWN"

# Generic toy/ecommerce product-form terms. This is not product hardcoding; it
# protects against sibling variants such as booster vs booster display, single
# item vs box/case, bundle vs standalone product, etc. Keep this list editable.
VARIANT_CONFLICT_TERMS = (
    "display", "booster display", "box", "case", "carton", "bundle",
    "multipack", "multi pack", "assortment", "blister", "tin",
    "starter deck", "deck", "elite trainer box", "trainer box",
    "collection box", "gift box", "mega pack", "value pack",
)

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScoreWeights:
    organic: float = 0.08
    ai: float = 0.12
    retailer: float = 0.10
    country: float = 0.10
    ean: float = 0.24
    title: float = 0.15
    page_type: float = 0.08
    scrape: float = 0.10
    identity: float = 0.25
    richness: float = 0.12

DEFAULT_SCORE_WEIGHTS = ScoreWeights()

RICHNESS_FIELD_WEIGHTS = {
    "specs": 0.18,
    "brand": 0.10,
    "manufacturer": 0.08,
    "structured_eans": 0.12,
    "description": 0.18,
    "price": 0.10,
    "images": 0.12,
    "availability": 0.06,
    "product_name": 0.06,
}
