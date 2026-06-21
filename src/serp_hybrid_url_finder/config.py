from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

from src.serp_hybrid_url_finder.constants import (
    ALLOW_GLOBAL_FALLBACK_DEFAULT,
    ALLOW_PROBABLE_AS_FINAL_DEFAULT,
    CRAWL_HEADLESS_DEFAULT,
    CRAWL_MIN_WORD_COUNT,
    CRAWL_PAGE_TIMEOUT_MS,
    CRAWL_VERBOSE_DEFAULT,
    DEFAULT_BACKOFF_SECONDS,
    DEFAULT_COUNTRY_CODE,
    DEFAULT_DEVICE,
    DEFAULT_ENV_FILE,
    DEFAULT_LANGUAGE_CODE,
    DEFAULT_MAX_CANDIDATES_FOR_AI,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_URLS_TO_SCRAPE,
    DEFAULT_NO_CACHE,
    DEFAULT_ORGANIC_NUM_RESULTS,
    DEFAULT_SCORE_WEIGHTS,
    DEFAULT_TIMEOUT_SECONDS,
    HIGH_CONFIDENCE_REQUIRES_JUSTIFICATION_DEFAULT,
    MAX_AI_MODE_CALLS_PER_PRODUCT,
    MAX_ORGANIC_SEARCH_CALLS_PER_PRODUCT,
    REQUIRE_IDENTITY_VERIFIED_DEFAULT,
    REQUIRE_SCRAPABLE_FINAL_DEFAULT,
    RICHNESS_MIN_GATE_DEFAULT,
    SCRAPE_ENABLED_DEFAULT,
    SERPAPI_API_KEY_ENV,
    ScoreWeights,
)
from src.serp_hybrid_url_finder.country_mapping import resolve_language
from src.serp_hybrid_url_finder.markets import MarketProfile



@dataclass(frozen=True)
class SerpAPIConfig:
    """Configuration shared by SerpAPI Google Search and Google AI Mode."""

    api_key: str
    country_code: str = DEFAULT_COUNTRY_CODE
    language_code: str = DEFAULT_LANGUAGE_CODE
    device: str = DEFAULT_DEVICE
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS
    no_cache: bool = DEFAULT_NO_CACHE
    location: Optional[str] = None
    organic_num_results: int = DEFAULT_ORGANIC_NUM_RESULTS

    @classmethod
    def from_env(
        cls,
        *,
        country_code: str = DEFAULT_COUNTRY_CODE,
        language_code: Optional[str] = None,
        device: str = DEFAULT_DEVICE,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        no_cache: bool = DEFAULT_NO_CACHE,
        location: Optional[str] = None,
        organic_num_results: int = DEFAULT_ORGANIC_NUM_RESULTS,
        env_file: Optional[str] = DEFAULT_ENV_FILE,
    ) -> "SerpAPIConfig":
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        api_key = os.getenv(SERPAPI_API_KEY_ENV)
        if not api_key:
            raise ValueError(
                f"{SERPAPI_API_KEY_ENV} not found. Create .env or export the variable."
            )

        # Auto-derive language from country if not explicitly provided
        country_code = country_code.lower()
        if language_code is None:
            try:
                language_code = resolve_language(country_code.upper())
            except KeyError:
                # Country not in mapping; fall back to default
                language_code = DEFAULT_LANGUAGE_CODE
        else:
            language_code = language_code.lower()

        return cls(
            api_key=api_key,
            country_code=country_code,
            language_code=language_code,
            device=device,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            no_cache=no_cache,
            location=location,
            organic_num_results=organic_num_results,
        )


@dataclass(frozen=True)
class PipelineConfig:
    """Runtime knobs for the hybrid product URL finder.
    
    Search Strategy:
    - max_organic_calls: 3-tier search (in-country exact, in-country adaptive, global fallback)
    - max_ai_mode_calls: AI validation + optional repair
    
    Identity Verification:
    - Title match is required (strong/partial)
    - EAN is optional (strength signal, not a blocker)
    - Pack size is ignored (irrelevant for product coding)
    - Richness heavily weighted in ranking (for product team extraction)
    """

    max_organic_calls: int = MAX_ORGANIC_SEARCH_CALLS_PER_PRODUCT
    max_ai_mode_calls: int = MAX_AI_MODE_CALLS_PER_PRODUCT
    max_candidates_for_ai: int = DEFAULT_MAX_CANDIDATES_FOR_AI
    run_ai_repair: bool = True
    repair_confidence_threshold: float = 0.75

    # crawl4ai scrape verification.
    scrape_enabled: bool = SCRAPE_ENABLED_DEFAULT
    require_scrapable_final: bool = REQUIRE_SCRAPABLE_FINAL_DEFAULT
    max_urls_to_scrape: int = DEFAULT_MAX_URLS_TO_SCRAPE
    crawl_headless: bool = CRAWL_HEADLESS_DEFAULT
    crawl_verbose: bool = CRAWL_VERBOSE_DEFAULT
    crawl_page_timeout_ms: int = CRAWL_PAGE_TIMEOUT_MS
    crawl_min_word_count: int = CRAWL_MIN_WORD_COUNT

    # Product-identity verification (the returned URL must be the CORRECT product).
    require_identity_verified: bool = REQUIRE_IDENTITY_VERIFIED_DEFAULT
    allow_probable_as_final: bool = ALLOW_PROBABLE_AS_FINAL_DEFAULT
    # Allow IDENTITY_WEAK (partial title match, no EAN) as a final result.
    # These are always flagged NEEDS_REVIEW and confidence-capped at 0.50.
    # Strongly recommended True for descriptive toy names (plush, pretend play,
    # sports) where title overlap is partial and EAN is often absent.
    allow_weak_as_final: bool = True
    high_confidence_requires_justification: bool = HIGH_CONFIDENCE_REQUIRES_JUSTIFICATION_DEFAULT

    # Country scope. allow_global_fallback=False (default) LOCKS results to the
    # requested country: the pipeline returns the best in-country product URL
    # (capped + flagged when weak) rather than silently substituting another
    # market. Set True to permit a verified out-of-country URL when nothing
    # suitable exists in-country (still penalised vs an in-country result).
    allow_global_fallback: bool = ALLOW_GLOBAL_FALLBACK_DEFAULT

    # Optional explicit market profile (language/locale heuristics). When None the
    # profile is resolved on the fly from each product's country_code.
    market_profile: Optional[MarketProfile] = None

    # Injectable confidence-model scoring weights.
    score_weights: ScoreWeights = DEFAULT_SCORE_WEIGHTS

    # Optional richness floor (0..1). 0.0 (default) never rejects for low
    # richness; richness only orders correct + scrapable candidates. Raise to
    # require a minimum amount of extractable product data on the returned page.
    min_richness: float = RICHNESS_MIN_GATE_DEFAULT
