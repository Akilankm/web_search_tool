"""Information-richness constants.

Richness measures how many useful, *scrapable* product attributes a page yields
for downstream product coding (brand, manufacturer, licence, specifications,
price, description, images...). It is a SEPARATE axis from confidence: confidence
answers "is this the correct product, in scope?" while richness answers "how much
usable product information can I extract from it?".

The selection policy uses richness as a strong preference among candidates that
already pass the hard correctness + scrapability gate.
"""

from __future__ import annotations

from typing import Final

# Weighted contribution of each attribute to the 0..1 richness score. Weights
# sum to 1.0 and emphasise the fields most useful for product coding (specs,
# brand, manufacturer) per the product-attribution use case.
RICHNESS_FIELD_WEIGHTS: Final[dict[str, float]] = {
    "specs": 0.22,
    "brand": 0.14,
    "manufacturer": 0.12,
    "structured_ean": 0.12,
    "description": 0.12,
    "price": 0.10,
    "images": 0.08,
    "availability": 0.05,
    "product_name": 0.05,
}

# Counts / lengths at which a field earns its full weight (partial credit below).
RICHNESS_SPECS_FULL_CREDIT_COUNT: Final[int] = 6
RICHNESS_IMAGES_FULL_CREDIT_COUNT: Final[int] = 3
RICHNESS_DESCRIPTION_FULL_CREDIT_CHARS: Final[int] = 200

RICHNESS_SCORE_ROUND_DIGITS: Final[int] = 4

# Optional hard gate: drop pages whose richness is below this floor. Default 0.0
# means "never reject for low richness" — a thin but correct + scrapable page is
# still acceptable when it is the only option (richness only decides ordering).
RICHNESS_MIN_GATE_DEFAULT: Final[float] = 0.0

# Caps on how much raw text/attribute payload is retained per page.
RICHNESS_DESCRIPTION_MAX_CHARS: Final[int] = 2_000
RICHNESS_MAX_SPEC_ROWS: Final[int] = 60
RICHNESS_MAX_SPEC_KEY_CHARS: Final[int] = 120
RICHNESS_MAX_SPEC_VALUE_CHARS: Final[int] = 400
RICHNESS_MAX_IMAGE_URLS: Final[int] = 20

# HTML spec-table parsing bounds (key/value cells).
RICHNESS_SPEC_TABLE_MAX_CELLS: Final[int] = 4

# JSON-LD property keys that map onto first-class richness fields.
JSONLD_BRAND_KEYS: Final[tuple[str, ...]] = ("brand",)
JSONLD_MANUFACTURER_KEYS: Final[tuple[str, ...]] = ("manufacturer",)
JSONLD_DESCRIPTION_KEYS: Final[tuple[str, ...]] = ("description",)
JSONLD_IMAGE_KEYS: Final[tuple[str, ...]] = ("image",)
# JSON-LD keys that, when present on a product node, are treated as generic spec
# attributes rather than first-class fields.
JSONLD_ATTRIBUTE_SKIP_KEYS: Final[frozenset[str]] = frozenset({
    "@context", "@type", "@id", "@graph", "name", "url", "offers",
    "brand", "manufacturer", "description", "image", "gtin13", "gtin12",
    "gtin14", "gtin8", "gtin", "ean", "barcode", "mpn", "sku", "review",
    "aggregaterating", "additionalproperty",
})
