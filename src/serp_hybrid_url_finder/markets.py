"""Market profiles: de-hardcoded, per-market language/locale heuristics.

Historically the quantity units (Czech ``KS``), currency terms (``CZK``/``PLN``),
soft-404 phrases (Czech/German) and title stopwords were hardcoded constants.
That made the system implicitly CZ/EU-only and impossible to extend to a new
market (e.g. Colombia) without editing scattered code.

A :class:`MarketProfile` packages every market-dependent heuristic in one place.
:data:`GENERIC_PROFILE` is a comprehensive, multilingual superset that works for
any country out of the box (it recognises English, Czech, German, Polish,
Hungarian and Spanish signals at once). Per-country overrides can be registered
on the fly via :class:`MarketProfileRegistry` without touching the engine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class MarketProfile:
    """All market/language dependent heuristics for one or more countries.

    Every field is data, not code: adding a market means adding a profile, never
    editing the verifier, scraper or ranker.
    """

    profile_id: str
    # ISO-3166 alpha-2 codes this profile is the preferred match for. Empty for
    # the generic/default profile that applies to any country.
    country_codes: Tuple[str, ...] = ()

    # Pack-size / quantity unit tokens. Entries may be regex fragments (e.g.
    # ``packs?``). Both accented and diacritic-folded spellings are kept because
    # different consumers fold text before matching.
    quantity_units: Tuple[str, ...] = ()

    # Currency tokens / symbols used to detect that a page exposes a price.
    currency_terms: Tuple[str, ...] = ()

    # Body phrases that indicate a soft-404 / "product not found" page.
    soft_404_phrases: Tuple[str, ...] = ()
    # Title/H1 phrases that indicate a soft-404 page.
    soft_404_title_phrases: Tuple[str, ...] = ()

    # Add-to-cart / buy phrases that corroborate a real, purchasable PDP.
    add_to_cart_phrases: Tuple[str, ...] = ()

    # Generic, non-distinctive tokens removed when computing title signatures.
    title_stopwords: frozenset[str] = field(default_factory=frozenset)

    def build_quantity_regex(self) -> str:
        """Regex with two capture groups: (count, unit).

        The group order is part of the contract consumed by the identity
        verifier (``group(1)`` = count, ``group(2)`` = unit).
        """
        units = "|".join(self.quantity_units) if self.quantity_units else r"(?!x)x"
        return rf"(\d{{1,4}})\s*[-]?\s*({units})\b"

    def build_price_regex(self) -> str:
        """Regex that matches ``<number><currency>`` or ``<currency><number>``."""
        terms = "|".join(re.escape(term) for term in self.currency_terms)
        if not terms:
            terms = r"(?!x)x"
        return (
            rf"\d[\d\s.,]{{0,12}}\s*(?:{terms})"
            rf"|(?:{terms})\s*\d"
        )

    def merged_with(self, override: "MarketProfile") -> "MarketProfile":
        """Return a new profile combining this base with ``override`` on top.

        Used to build a country-specific profile that extends the generic one:
        the override's tuples are appended (deduplicated) and stopwords unioned.
        """

        def _dedupe(*groups: Tuple[str, ...]) -> Tuple[str, ...]:
            seen: dict[str, None] = {}
            for group in groups:
                for item in group:
                    seen.setdefault(item, None)
            return tuple(seen.keys())

        return replace(
            override,
            quantity_units=_dedupe(self.quantity_units, override.quantity_units),
            currency_terms=_dedupe(self.currency_terms, override.currency_terms),
            soft_404_phrases=_dedupe(self.soft_404_phrases, override.soft_404_phrases),
            soft_404_title_phrases=_dedupe(
                self.soft_404_title_phrases, override.soft_404_title_phrases
            ),
            add_to_cart_phrases=_dedupe(
                self.add_to_cart_phrases, override.add_to_cart_phrases
            ),
            title_stopwords=frozenset(self.title_stopwords | override.title_stopwords),
        )


# =============================================================================
# Generic, multilingual default profile
#
# Superset of the original CZ/DE/EN heuristics plus Spanish (Colombia, LATAM),
# Polish and Hungarian signals. Recognising more languages only ever broadens
# detection in the safe direction, so no existing market regresses.
# =============================================================================

GENERIC_PROFILE: MarketProfile = MarketProfile(
    profile_id="generic",
    country_codes=(),
    quantity_units=(
        # English
        "pcs", "pc", "pck", "packs?", "pieces?", "piece", "count", "ct", "pack",
        # Czech / Slovak (kusů = pieces)
        "ks", "kusu", "kusů", "kpl",
        # German (Stück)
        "stk", "stück", "stuck",
        # Polish (sztuk)
        "szt",
        # Spanish (unidades / piezas)
        "unidades", "unidad", "uds", "und", "piezas", "pieza", "pzas", "pza",
    ),
    currency_terms=(
        # Czech / EU
        "kč", "czk", "€", "eur", "zł", "pln", "£", "gbp", "$", "usd", "huf", "ft",
        # Spanish / LATAM (Colombian peso, Mexican peso, generic)
        "cop", "mxn", "ars", "clp", "pen", "peso", "pesos",
    ),
    soft_404_phrases=(
        # English
        "page not found", "page does not exist", "not found",
        "no longer available", "no results", "no products found",
        "this product is no longer", "product not found",
        # Czech
        "stránka nenalezena", "stranka nenalezena", "nenalezeno",
        "nebyla nalezena", "neexistuje", "produkt nenalezen",
        "není dostupné", "neni dostupne", "není k dispozici",
        "zboží nebylo nalezeno", "zbozi nebylo nalezeno",
        # German
        "seite nicht gefunden", "nicht gefunden",
        # Spanish
        "página no encontrada", "pagina no encontrada", "no encontrado",
        "no encontrada", "producto no encontrado", "no disponible",
        "no existe", "sin resultados", "no se encontraron productos",
        "agotado",
    ),
    soft_404_title_phrases=(
        "not found", "404", "nenalezena", "nenalezeno", "nicht gefunden",
        "no encontrada", "no encontrado", "no existe",
    ),
    add_to_cart_phrases=(
        # English
        "add to cart", "add to basket", "add-to-cart", "buy now",
        # Czech
        "do košíku", "do kosiku", "koupit",
        # German
        "in den warenkorb",
        # Polish
        "do koszyka",
        # Hungarian
        "kosárba",
        # Spanish
        "añadir al carrito", "agregar al carrito", "comprar", "agregar al cesto",
    ),
    title_stopwords=frozenset({
        # English
        "the", "and", "for", "with", "set", "pack", "new", "original",
        "toy", "toys", "figure", "kit",
        # Czech / German function + generic words
        "figurka", "se", "von", "der", "die", "das", "mit", "und", "pro",
        # Spanish function words (longer than the 3-char floor still get removed)
        "para", "con", "los", "las", "una", "del",
    }),
)


@dataclass
class MarketProfileRegistry:
    """Resolves a :class:`MarketProfile` for a country, with on-the-fly overrides.

    ``resolve`` always returns a usable profile: a registered country-specific
    profile when present, otherwise the generic default. New markets can be
    added at runtime with ``register`` (no code change required).
    """

    default: MarketProfile = GENERIC_PROFILE
    _by_country: Dict[str, MarketProfile] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for profile in (self.default,):
            for code in profile.country_codes:
                self._by_country.setdefault(code.lower().strip(), profile)

    def resolve(self, country_code: Optional[str]) -> MarketProfile:
        if not country_code:
            return self.default
        return self._by_country.get(country_code.lower().strip(), self.default)

    def register(
        self,
        profile: MarketProfile,
        *,
        country_codes: Optional[Tuple[str, ...]] = None,
        extend_default: bool = True,
    ) -> MarketProfile:
        """Register ``profile`` for its country codes.

        When ``extend_default`` is True the profile is merged on top of the
        generic default so a country override only needs to declare its extra
        market-specific terms, inheriting everything else.
        """
        effective = self.default.merged_with(profile) if extend_default else profile
        codes = country_codes or profile.country_codes
        for code in codes:
            self._by_country[code.lower().strip()] = effective
        return effective


# Module-level default registry used when no custom registry is injected.
MARKET_REGISTRY: MarketProfileRegistry = MarketProfileRegistry(default=GENERIC_PROFILE)


def resolve_market_profile(
    country_code: Optional[str],
    *,
    registry: Optional[MarketProfileRegistry] = None,
) -> MarketProfile:
    """Convenience resolver used across the pipeline."""
    return (registry or MARKET_REGISTRY).resolve(country_code)
