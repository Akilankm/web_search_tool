from __future__ import annotations

import json
import os
import re
from pathlib import Path
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from src.product_evidence_harness.contracts import ProductQuery
from src.product_evidence_harness.identity.normalizer import fold_text, join_unique, segment_compact_text, tokens

TAXONOMY_PATH_ENV = "PRODUCT_HARNESS_PRODUCT_IDENTITY_TAXONOMY"
DEFAULT_TAXONOMY_FILE = Path(__file__).resolve().parents[1] / "configs" / "product_identity_taxonomy.json"


def _load_taxonomy() -> dict[str, Any]:
    try:
        path = Path(os.getenv(TAXONOMY_PATH_ENV) or DEFAULT_TAXONOMY_FILE)
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

_TAXONOMY = _load_taxonomy()

# Generic lexicons. These are category/platform primitives, not product-specific rules.
COLOR_TERMS = {
    "black", "white", "red", "blue", "green", "yellow", "orange", "pink", "purple", "violet",
    "lilac", "brown", "grey", "gray", "silver", "gold", "transparent", "clear",
    "schwarz", "weiss", "weiß", "rot", "blau", "grun", "grün", "gelb", "rosa", "lila", "flieder",
    "morado", "rojo", "azul", "verde", "amarillo", "negro", "blanco", "gris", "dorado",
    "rouge", "bleu", "vert", "jaune", "noir", "blanc", "gris", "violet",
}

PRODUCT_FORM_FAMILIES: dict[str, set[str]] = {
    "card": {"card", "cards", "karte", "karten", "cartes", "tarjeta", "tarjetas", "cartas"},
    "paper": {"paper", "papier", "bastelpapier", "papel", "carta"},
    "booster": {"booster", "pack", "packet", "sachet"},
    "display": {"display", "box", "case", "carton", "booster display", "display box"},
    "figure": {"figure", "figurine", "figurka", "figurka", "figur", "action figure"},
    "set": {"set", "kit", "build set", "building set", "souprava", "sada"},
    "puzzle": {"puzzle", "puzle", "jigsaw"},
    "game": {"game", "spiel", "hra", "juego", "jeu"},
    "book": {"book", "buch", "libro", "livre", "kniha"},
    "refill": {"refill", "nachfüllung", "nachfullung", "recambio", "recharge"},
    "accessory": {"accessory", "zubehör", "zubehor", "accesorio", "accessoire"},
}

EDITION_LANGUAGE_TERMS = {"de", "en", "fr", "it", "cz", "cs", "es", "pl", "nl", "edition", "version", "ausgabe"}
if _TAXONOMY.get("colors"):
    COLOR_TERMS = set(map(str, _TAXONOMY.get("colors", [])))
if _TAXONOMY.get("product_form_families"):
    PRODUCT_FORM_FAMILIES = {str(k): set(map(str, v)) for k, v in _TAXONOMY.get("product_form_families", {}).items() if isinstance(v, list)}
if _TAXONOMY.get("edition_language_terms"):
    EDITION_LANGUAGE_TERMS = set(map(str, _TAXONOMY.get("edition_language_terms", [])))
SIZE_FORMAT_REGEX = re.compile(r"(?<![a-z0-9])([abc][0-9]{1,2}|\d+(?:[.,]\d+)?\s?(?:mm|cm|m|inch|in|ml|l|g|kg))(?![a-z0-9])", re.I)
QUANTITY_REGEX = re.compile(r"(?<![a-z0-9])(\d{1,4})\s*(pcs?|pieces?|packs?|count|ct|ks|stk|stück|stuck|szt|unidades|unidad|uds|und|piezas?|pzas?|pza)(?![a-z0-9])", re.I)

@dataclass(frozen=True)
class ProductIdentityGraph:
    raw_main_text: str
    normalized_main_text: str
    expanded_product_name_candidates: tuple[str, ...] = ()
    brand_candidates: tuple[str, ...] = ()
    manufacturer_candidates: tuple[str, ...] = ()
    model_or_series_terms: tuple[str, ...] = ()
    product_form_terms: tuple[str, ...] = ()
    product_form_families: tuple[str, ...] = ()
    variant_terms: tuple[str, ...] = ()
    size_terms: tuple[str, ...] = ()
    color_terms: tuple[str, ...] = ()
    quantity_terms: tuple[str, ...] = ()
    language_or_edition_terms: tuple[str, ...] = ()
    must_match_terms: tuple[str, ...] = ()
    soft_match_terms: tuple[str, ...] = ()
    conflict_terms: tuple[str, ...] = ()
    input_ean: Optional[str] = None
    country_code: str = ""
    retailer_constraint: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def search_name(self) -> str:
        return self.expanded_product_name_candidates[0] if self.expanded_product_name_candidates else self.normalized_main_text


@dataclass(frozen=True)
class ProductIdentityGraphBuilder:
    max_must_terms: int = 10

    def build(self, query: ProductQuery, *, llm_plan: Any | None = None) -> ProductIdentityGraph:
        raw = query.main_text or ""
        expanded = segment_compact_text(raw)
        toks = tokens(raw, min_len=2)
        sizes = self._extract_sizes(expanded)
        qtys = self._extract_quantities(expanded)
        colors = self._extract_colors(expanded)
        forms, families = self._extract_forms(expanded)
        editions = tuple(t for t in toks if t in EDITION_LANGUAGE_TERMS)
        models = self._extract_model_or_series_terms(expanded, toks)
        llm_critical = tuple(getattr(llm_plan, "critical_terms", ()) or ()) if llm_plan else ()
        llm_variant = tuple(getattr(llm_plan, "variant_terms_to_preserve", ()) or ()) if llm_plan else ()
        llm_expanded = getattr(llm_plan, "expanded_main_text", "") if llm_plan else ""
        llm_negative = tuple(getattr(llm_plan, "negative_terms", ()) or ()) if llm_plan else ()

        # Product-grade identity rule: model/set/SKU-like terms and hard
        # variant attributes are first-class exactness terms. They are generic
        # identifiers, not product-specific hardcoding.
        must = join_unique([
            *models, *llm_critical, *sizes, *colors, *qtys, *forms, *self._distinctive_terms(toks)
        ])[: self.max_must_terms]
        variant = join_unique([*llm_variant, *sizes, *colors, *qtys, *editions, *forms])
        expanded_candidates = join_unique([llm_expanded, expanded, raw])
        return ProductIdentityGraph(
            raw_main_text=raw,
            normalized_main_text=expanded,
            expanded_product_name_candidates=expanded_candidates,
            model_or_series_terms=models,
            product_form_terms=forms,
            product_form_families=families,
            variant_terms=variant,
            size_terms=sizes,
            color_terms=colors,
            quantity_terms=qtys,
            language_or_edition_terms=editions,
            must_match_terms=must,
            soft_match_terms=tuple(t for t in toks if t not in {fold_text(x) for x in must})[:8],
            conflict_terms=join_unique(llm_negative),
            input_ean=query.ean,
            country_code=query.country_code,
            retailer_constraint=query.retailer_name,
        )

    def _extract_sizes(self, text: str) -> tuple[str, ...]:
        return join_unique(m.group(1).replace(" ", "") for m in SIZE_FORMAT_REGEX.finditer(fold_text(text)))

    def _extract_quantities(self, text: str) -> tuple[str, ...]:
        return join_unique(f"{m.group(1)} {m.group(2).lower()}" for m in QUANTITY_REGEX.finditer(fold_text(text)))

    def _extract_colors(self, text: str) -> tuple[str, ...]:
        ft = fold_text(text)
        return join_unique(c for c in COLOR_TERMS if re.search(rf"(?<![a-z0-9]){re.escape(fold_text(c))}(?![a-z0-9])", ft))

    def _extract_forms(self, text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
        ft = fold_text(text)
        terms: list[str] = []
        families: list[str] = []
        for family, lexemes in PRODUCT_FORM_FAMILIES.items():
            for lex in sorted(lexemes, key=len, reverse=True):
                if re.search(rf"(?<![a-z0-9]){re.escape(fold_text(lex))}(?![a-z0-9])", ft):
                    terms.append(lex)
                    families.append(family)
                    break
        return join_unique(terms), join_unique(families)

    def _extract_model_or_series_terms(self, text: str, toks: list[str]) -> tuple[str, ...]:
        """Extract generic model/set/SKU-like identity terms.

        These terms are treated as hard identity evidence because products often
        differ only by a set number, model code, assortment code, or numeric
        line identifier. This is category-agnostic and does not encode any
        retailer or product-specific rule.
        """
        found: list[str] = []
        for token in toks:
            # Alphanumeric codes: 41731, 75313, A1078175774, 650392, etc.
            if re.fullmatch(r"\d{4,}", token):
                found.append(token)
            elif re.search(r"[a-z]", token) and re.search(r"\d", token) and len(token) >= 4:
                found.append(token)
        # Also preserve hyphenated/dotted model chunks from raw text.
        for match in re.findall(r"(?<![a-z0-9])([a-z0-9]+(?:[-_.][a-z0-9]+)+)(?![a-z0-9])", fold_text(text)):
            if re.search(r"\d", match):
                found.append(match)
        return join_unique(found)[:6]

    def _distinctive_terms(self, toks: list[str]) -> tuple[str, ...]:
        stop = {"the", "and", "for", "with", "von", "der", "die", "das", "und", "mit", "de", "en", "fr"}
        out = []
        for t in toks:
            if t in stop:
                continue
            if re.fullmatch(r"[abc]\d{1,2}", t):
                out.append(t)
            elif re.fullmatch(r"\d{4,}", t):
                out.append(t)
            elif len(t) >= 3 and not t.isdigit():
                out.append(t)
        return tuple(out[: self.max_must_terms])
