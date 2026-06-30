from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Optional

from dotenv import load_dotenv

from src.product_evidence_harness.constants import DEFAULT_SCORE_WEIGHTS, SERPAPI_API_KEY_ENV, ScoreWeights
from src.product_evidence_harness.contracts import DiscoveryMode


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


@dataclass(frozen=True)
class SerpAPIConfig:
    api_key: str
    country_code: str = "us"
    language_code: str = "en"
    device: str = "desktop"
    timeout_seconds: int = 60
    max_retries: int = 3
    backoff_seconds: float = 2.0
    no_cache: bool = False
    location: Optional[str] = None
    organic_num_results: int = 100

    @classmethod
    def from_env(
        cls,
        *,
        country_code: str = "US",
        language_code: str = "en",
        env_file: Optional[str] = ".env",
        **overrides,
    ) -> "SerpAPIConfig":
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()
        api_key = os.getenv(SERPAPI_API_KEY_ENV)
        if not api_key:
            raise ValueError(f"{SERPAPI_API_KEY_ENV} not found in environment")
        return cls(
            api_key=api_key,
            country_code=country_code.lower(),
            language_code=language_code.lower(),
            organic_num_results=_env_int("PRODUCT_HARNESS_SERP_RESULTS", int(overrides.pop("organic_num_results", 100))),
            **overrides,
        )


@dataclass(frozen=True)
class HarnessPolicy:
    discovery_mode: DiscoveryMode = DiscoveryMode.PRODUCT_EVIDENCE
    require_scrapable_primary: bool = True
    allow_global_fallback: bool = True
    allow_ai_only_reference: bool = False
    allow_pack_size_mismatch: bool = False
    allow_ean_conflict: bool = True
    min_verified_confidence: float = 0.80
    min_review_confidence: float = 0.30
    min_title_overlap: float = 0.35
    min_exact_title_overlap: float = 0.75
    ean_conflict_confidence_cap: float = 0.82
    high_confidence_requires_hard_evidence: bool = True
    require_country_specific_before_global: bool = True
    requested_retailer_first: bool = True
    requested_retailer_min_scrapes_for_escape: int = 2
    requested_retailer_min_richness_for_evidence: float = 0.30
    require_llm_exact_match_for_final: bool = False
    return_rejected_reference_as_product_url: bool = False


@dataclass(frozen=True)
class HarnessBudgetConfig:
    max_organic_searches: int = 3
    max_ai_mode_searches: int = 1
    max_scrapes: int = 180
    max_iterations: int = 240


@dataclass(frozen=True)
class TournamentConfig:
    enabled: bool = False
    max_serp_credits: int = 4
    candidate_pool: int = 150
    preflight_top_k: int = 60
    batch_size: int = 20
    max_batches: int = 3
    finalist_count: int = 5
    early_stop: bool = True
    early_stop_margin: float = 0.15
    require_production_ready: bool = True

    @classmethod
    def from_env(cls) -> "TournamentConfig":
        max_serp = _env_int("PRODUCT_HARNESS_TOURNAMENT_MAX_SERP_CREDITS", 4)
        # Hard safety cap requested by business: tournament mode must not exceed 4 SerpAPI searches per product.
        max_serp = max(0, min(4, max_serp))
        return cls(
            enabled=_env_bool("PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE", False),
            max_serp_credits=max_serp,
            candidate_pool=_env_int("PRODUCT_HARNESS_TOURNAMENT_CANDIDATE_POOL", 150),
            preflight_top_k=_env_int("PRODUCT_HARNESS_TOURNAMENT_PREFLIGHT_TOP_K", 60),
            batch_size=_env_int("PRODUCT_HARNESS_TOURNAMENT_BATCH_SIZE", 20),
            max_batches=_env_int("PRODUCT_HARNESS_TOURNAMENT_MAX_BATCHES", 3),
            finalist_count=_env_int("PRODUCT_HARNESS_TOURNAMENT_FINALIST_COUNT", 5),
            early_stop=_env_bool("PRODUCT_HARNESS_TOURNAMENT_EARLY_STOP", True),
            early_stop_margin=_env_float("PRODUCT_HARNESS_TOURNAMENT_EARLY_STOP_MARGIN", 0.15),
            require_production_ready=_env_bool("PRODUCT_HARNESS_TOURNAMENT_REQUIRE_PRODUCTION_READY", True),
        )


@dataclass(frozen=True)
class HarnessConfig:
    budget: HarnessBudgetConfig = field(default_factory=HarnessBudgetConfig)
    policy: HarnessPolicy = field(default_factory=HarnessPolicy)
    tournament: TournamentConfig = field(default_factory=TournamentConfig)
    score_weights: ScoreWeights = DEFAULT_SCORE_WEIGHTS
    max_candidates_for_ai: int = 12
    max_candidate_pool: int = 300
    scrape_enabled: bool = True
    crawl_headless: bool = True
    crawl_verbose: bool = False
    crawl_page_timeout_ms: int = 45000
    crawl_min_word_count: int = 20
    scrape_concurrency: int = 6
    static_fetch_first: bool = True
    browser_fallback_only: bool = True
    static_timeout_seconds: int = 8
    max_requested_retailer_scrapes_per_batch: int = 6
    max_country_scrapes_per_batch: int = 30
    max_global_scrapes_per_batch: int = 12
    write_outputs: bool = True
    output_dir: str = "output"
    write_artifacts: bool = False
    artifact_dir: Optional[str] = None
    country_profile_path: Optional[str] = None
    write_markdown_reports: bool = True
    write_trace_json: bool = True
    write_debug_csvs: bool = False

    enable_llm_adjudication: bool = False
    enable_llm_search_planning: bool = False
    enable_llm_search_feedback: bool = False
    llm_max_calls_per_product: int = 4
    llm_search_plan_max_queries: int = 6
    llm_search_feedback_max_queries: int = 4
    llm_search_feedback_max_rounds: int = 2
    llm_adjudicate_top_k: int = 3
    llm_use_images: bool = True
    llm_one_image_per_call: bool = True
    llm_image_detail: str = "high"
    llm_payload_reduction_enabled: bool = True
    llm_require_exact_match_for_final: bool = False
    return_best_available_url: bool = True
    return_rejected_reference_as_product_url: bool = False
    reserve_llm_call_for_adjudication: bool = True
    global_fallback_language_code: str = "en"
    global_fallback_country_code: str = ""

    @classmethod
    def from_env(cls, env_file: Optional[str] = ".env") -> "HarnessConfig":
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        tournament = TournamentConfig.from_env()
        if tournament.enabled:
            budget = HarnessBudgetConfig(
                max_organic_searches=tournament.max_serp_credits,
                max_ai_mode_searches=0,
                max_scrapes=_env_int("PRODUCT_HARNESS_MAX_SCRAPES", 180),
                max_iterations=_env_int("PRODUCT_HARNESS_MAX_ITERATIONS", 240),
            )
        else:
            budget = HarnessBudgetConfig(
                max_organic_searches=_env_int("PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES", 3),
                max_ai_mode_searches=_env_int("PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES", 1),
                max_scrapes=_env_int("PRODUCT_HARNESS_MAX_SCRAPES", 180),
                max_iterations=_env_int("PRODUCT_HARNESS_MAX_ITERATIONS", 240),
            )
        llm_enabled = _env_bool("PRODUCT_HARNESS_ENABLE_LLM", False) or _env_bool("PRODUCT_HARNESS_ENABLE_LLM_ADJUDICATION", False)
        policy = HarnessPolicy(
            require_llm_exact_match_for_final=_env_bool("PRODUCT_HARNESS_REQUIRE_LLM_EXACT_MATCH", False),
            allow_global_fallback=_env_bool("PRODUCT_HARNESS_ALLOW_GLOBAL_FALLBACK", True),
            require_country_specific_before_global=_env_bool("PRODUCT_HARNESS_COUNTRY_FIRST", True),
            requested_retailer_first=_env_bool("PRODUCT_HARNESS_REQUESTED_RETAILER_FIRST", True),
            requested_retailer_min_scrapes_for_escape=_env_int("PRODUCT_HARNESS_REQUESTED_RETAILER_MIN_SCRAPES_FOR_ESCAPE", 2),
            requested_retailer_min_richness_for_evidence=_env_float("PRODUCT_HARNESS_REQUESTED_RETAILER_MIN_RICHNESS_FOR_EVIDENCE", 0.30),
            allow_ean_conflict=_env_bool("PRODUCT_HARNESS_ALLOW_EAN_CONFLICT", True),
            min_review_confidence=_env_float("PRODUCT_HARNESS_MIN_REVIEW_CONFIDENCE", 0.30),
            min_verified_confidence=_env_float("PRODUCT_HARNESS_MIN_VERIFIED_CONFIDENCE", 0.80),
            return_rejected_reference_as_product_url=_env_bool("PRODUCT_HARNESS_RETURN_REJECTED_REFERENCE_AS_PRODUCT_URL", False),
        )
        return cls(
            budget=budget,
            policy=policy,
            tournament=tournament,
            max_candidate_pool=_env_int("PRODUCT_HARNESS_MAX_CANDIDATE_POOL", 300),
            scrape_concurrency=_env_int("PRODUCT_HARNESS_SCRAPE_CONCURRENCY", 6),
            static_fetch_first=_env_bool("PRODUCT_HARNESS_STATIC_FETCH_FIRST", True),
            browser_fallback_only=_env_bool("PRODUCT_HARNESS_BROWSER_FALLBACK_ONLY", True),
            static_timeout_seconds=_env_int("PRODUCT_HARNESS_STATIC_TIMEOUT_SECONDS", 8),
            crawl_page_timeout_ms=_env_int("PRODUCT_HARNESS_CRAWL_PAGE_TIMEOUT_MS", 45000),
            max_requested_retailer_scrapes_per_batch=_env_int("PRODUCT_HARNESS_MAX_REQUESTED_RETAILER_SCRAPES", 6),
            max_country_scrapes_per_batch=_env_int("PRODUCT_HARNESS_MAX_COUNTRY_SCRAPES", 30),
            max_global_scrapes_per_batch=_env_int("PRODUCT_HARNESS_MAX_GLOBAL_SCRAPES", 12),
            output_dir=os.getenv("PRODUCT_HARNESS_OUTPUT_DIR", "output"),
            write_outputs=_env_bool("PRODUCT_HARNESS_WRITE_OUTPUTS", True),
            write_markdown_reports=_env_bool("PRODUCT_HARNESS_WRITE_MARKDOWN_REPORTS", True),
            write_trace_json=_env_bool("PRODUCT_HARNESS_WRITE_TRACE_JSON", True),
            write_debug_csvs=_env_bool("PRODUCT_HARNESS_WRITE_DEBUG_CSVS", False),
            country_profile_path=os.getenv("PRODUCT_HARNESS_COUNTRY_PROFILES") or None,
            enable_llm_adjudication=llm_enabled,
            enable_llm_search_planning=_env_bool("PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING", llm_enabled),
            enable_llm_search_feedback=_env_bool("PRODUCT_HARNESS_ENABLE_LLM_SEARCH_FEEDBACK", llm_enabled),
            llm_max_calls_per_product=_env_int("PRODUCT_HARNESS_LLM_MAX_CALLS_PER_PRODUCT", 4),
            llm_search_plan_max_queries=_env_int("PRODUCT_HARNESS_LLM_SEARCH_PLAN_MAX_QUERIES", 6),
            llm_search_feedback_max_queries=_env_int("PRODUCT_HARNESS_LLM_SEARCH_FEEDBACK_MAX_QUERIES", 4),
            llm_search_feedback_max_rounds=_env_int("PRODUCT_HARNESS_LLM_SEARCH_FEEDBACK_MAX_ROUNDS", 2),
            llm_adjudicate_top_k=_env_int("PRODUCT_HARNESS_LLM_ADJUDICATE_TOP_K", 3),
            llm_use_images=_env_bool("PRODUCT_HARNESS_LLM_USE_IMAGES", True),
            llm_one_image_per_call=True,
            llm_image_detail=os.getenv("PRODUCT_HARNESS_LLM_IMAGE_DETAIL", "high"),
            llm_payload_reduction_enabled=_env_bool("PRODUCT_HARNESS_LLM_PAYLOAD_REDUCTION", True),
            llm_require_exact_match_for_final=_env_bool("PRODUCT_HARNESS_REQUIRE_LLM_EXACT_MATCH", False),
            return_best_available_url=_env_bool("PRODUCT_HARNESS_RETURN_BEST_AVAILABLE_URL", True),
            return_rejected_reference_as_product_url=_env_bool("PRODUCT_HARNESS_RETURN_REJECTED_REFERENCE_AS_PRODUCT_URL", False),
            reserve_llm_call_for_adjudication=_env_bool("PRODUCT_HARNESS_RESERVE_LLM_CALL_FOR_ADJUDICATION", True),
            global_fallback_language_code=os.getenv("PRODUCT_HARNESS_GLOBAL_FALLBACK_LANGUAGE", "en"),
            global_fallback_country_code=os.getenv("PRODUCT_HARNESS_GLOBAL_FALLBACK_COUNTRY", ""),
        )

    def with_effective_policy(self) -> "HarnessConfig":
        return replace(
            self,
            policy=replace(
                self.policy,
                require_llm_exact_match_for_final=self.llm_require_exact_match_for_final
                or self.policy.require_llm_exact_match_for_final,
            ),
        )


PipelineConfig = HarnessConfig
