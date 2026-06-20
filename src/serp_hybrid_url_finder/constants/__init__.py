"""Configuration constants for the hybrid product-URL finder.

This package replaces the former monolithic ``constants.py`` with a logical,
domain-split layout. Each submodule owns one concern:

- :mod:`.env`        environment / secret handling
- :mod:`.budget`     per-product call budget
- :mod:`.serpapi`    SerpAPI endpoints, params and response keys
- :mod:`.query`      organic + AI-mode query construction
- :mod:`.ai_evidence` AI-mode evidence parsing
- :mod:`.urls`       URL extraction / validation / domain blocking
- :mod:`.scraping`   crawl4ai scrape-verification
- :mod:`.identity`   product-identity verification verdicts
- :mod:`.scoring`    ranker weights, thresholds and confidence caps
- :mod:`.richness`   information-richness scoring
- :mod:`.reasons`    human-readable match reasons
- :mod:`.logging`    logging / Rich-printing constants

Every public name is re-exported here, so existing imports of the form
``from serp_hybrid_url_finder.constants import X`` continue to work unchanged.

Market/language-specific heuristics (quantity units, currency terms, soft-404
phrases, title stopwords) now live as data on
:class:`serp_hybrid_url_finder.markets.MarketProfile`. For backward compatibility
the legacy module-level constants (``QUANTITY_REGEX``, ``PRICE_REGEX``,
``SOFT_404_PHRASES`` ...) are derived here from the generic default profile.
"""

from __future__ import annotations

from serp_hybrid_url_finder.markets import (
    GENERIC_PROFILE,
    MARKET_REGISTRY,
    MarketProfile,
    MarketProfileRegistry,
    resolve_market_profile,
)

from .ai_evidence import *  # noqa: F401,F403
from .budget import *  # noqa: F401,F403
from .env import *  # noqa: F401,F403
from .identity import *  # noqa: F401,F403
from .logging import *  # noqa: F401,F403
from .query import *  # noqa: F401,F403
from .reasons import *  # noqa: F401,F403
from .richness import *  # noqa: F401,F403
from .scoring import *  # noqa: F401,F403
from .scraping import *  # noqa: F401,F403
from .serpapi import *  # noqa: F401,F403
from .urls import *  # noqa: F401,F403

# ---------------------------------------------------------------------------
# Backward-compatible, market-derived aliases.
#
# These were hardcoded module-level constants in the legacy ``constants.py``.
# They are now derived from the generic multilingual market profile so existing
# consumers (scraper, identity verifier) keep working while the engine itself
# resolves a per-country profile on the fly.
# ---------------------------------------------------------------------------
QUANTITY_REGEX: str = GENERIC_PROFILE.build_quantity_regex()
PRICE_REGEX: str = GENERIC_PROFILE.build_price_regex()
SOFT_404_PHRASES: tuple[str, ...] = GENERIC_PROFILE.soft_404_phrases
SOFT_404_TITLE_PHRASES: tuple[str, ...] = GENERIC_PROFILE.soft_404_title_phrases
ADD_TO_CART_PHRASES: tuple[str, ...] = GENERIC_PROFILE.add_to_cart_phrases
TITLE_STOPWORDS: frozenset[str] = GENERIC_PROFILE.title_stopwords
