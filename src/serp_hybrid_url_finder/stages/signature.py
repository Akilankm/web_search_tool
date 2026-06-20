from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from serp_hybrid_url_finder.models import ProductQuery, ProductSignature

_TOKEN_PATTERN = re.compile(r"[\wÀ-ž]+", re.UNICODE)
_DIGIT_PATTERN = re.compile(r"\d+")


def fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    asciiish = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", asciiish.lower()).strip()


@dataclass(frozen=True)
class ProductSignatureExtractor:
    """Extracts query/identity signals from main_text without locale tables."""

    min_token_len: int = 3
    max_tokens: int = 12

    def extract(self, product: ProductQuery) -> ProductSignature:
        normalized = fold_text(product.main_text)
        raw_tokens = [fold_text(token) for token in _TOKEN_PATTERN.findall(product.main_text)]
        candidates: list[str] = []
        seen: set[str] = set()
        for token in raw_tokens:
            if not token or token in seen:
                continue
            if token.isdigit():
                continue
            if len(token) < self.min_token_len:
                continue
            # Dynamic informativeness: avoid tiny/alphabetically-flat tokens while
            # keeping brand/model/product-family words across all languages.
            if len(set(token)) < 2:
                continue
            seen.add(token)
            candidates.append(token)
        numeric_tokens = tuple(dict.fromkeys(_DIGIT_PATTERN.findall(normalized)))
        ean = re.sub(r"\D", "", product.ean or "") or None
        fingerprint_src = "|".join([normalized, product.country_code.upper(), ean or "", product.retailer_name or ""])
        fingerprint = hashlib.sha256(fingerprint_src.encode("utf-8")).hexdigest()[:16]
        return ProductSignature(
            raw_text=product.main_text,
            normalized_text=normalized,
            distinctive_tokens=tuple(candidates[: self.max_tokens]),
            numeric_tokens=numeric_tokens,
            ean=ean,
            fingerprint=fingerprint,
        )
