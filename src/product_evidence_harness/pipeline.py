from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

from loguru import logger

from src.product_evidence_harness.artifacts import ArtifactWriter
from src.product_evidence_harness.budget import BudgetTracker
from src.product_evidence_harness.candidate_store import CandidateStore
from src.product_evidence_harness.config import HarnessConfig, SerpAPIConfig
from src.product_evidence_harness.contracts import HarnessTrace, ProductQuery, ProductSearchState, ProductURLMatch
from src.product_evidence_harness.country_profiles import CountryProfileRegistry
from src.product_evidence_harness.elite import EnterpriseEvidenceEngine
from src.product_evidence_harness.evidence_extractor import EvidenceExtractor
from src.product_evidence_harness.executor import HarnessExecutor
from src.product_evidence_harness.identity_verifier import ProductIdentityVerifier
from src.product_evidence_harness.identity.graph import ProductIdentityGraphBuilder
from src.product_evidence_harness.loop import BoundedHarnessLoop
from src.product_evidence_harness.llm.adjudicator import ExactProductLLMAdjudicator
from src.product_evidence_harness.llm.search_planner import LLMSearchPlanner
from src.product_evidence_harness.planner import HarnessPlanner
from src.product_evidence_harness.query_builder import QueryBuilder
from src.product_evidence_harness.ranker import ProductURLRanker
from src.product_evidence_harness.scraper import CrawlScraper
from src.product_evidence_harness.selector import FinalSelector
from src.product_evidence_harness.serp_clients import GoogleAIModeClient, GoogleOrganicSearchClient


@dataclass
class ProductEvidenceHarness:
    serp_config: SerpAPIConfig
    config: HarnessConfig = field(default_factory=HarnessConfig)
    organic_client: Optional[GoogleOrganicSearchClient] = None
    ai_client: Optional[GoogleAIModeClient] = None
    scraper: Optional[CrawlScraper] = None
    candidate_store: Optional[CandidateStore] = None
    query_builder: Optional[QueryBuilder] = None
    verifier: Optional[ProductIdentityVerifier] = None
    ranker: Optional[ProductURLRanker] = None
    selector: Optional[FinalSelector] = None
    evidence_extractor: Optional[EvidenceExtractor] = None
    country_profiles: Optional[CountryProfileRegistry] = None
    llm_adjudicator: Optional[ExactProductLLMAdjudicator] = None
    llm_search_planner: Optional[LLMSearchPlanner] = None
    enterprise_engine: Optional[EnterpriseEvidenceEngine] = None

    def __post_init__(self) -> None:
        self.country_profiles = self.country_profiles or CountryProfileRegistry.load(self.config.country_profile_path)
        self.organic_client = self.organic_client or GoogleOrganicSearchClient(self.serp_config)
        self.ai_client = self.ai_client or GoogleAIModeClient(self.serp_config)
        self.scraper = self.scraper or CrawlScraper(
            headless=self.config.crawl_headless,
            verbose=self.config.crawl_verbose,
            page_timeout_ms=self.config.crawl_page_timeout_ms,
            min_word_count=self.config.crawl_min_word_count,
            scrape_concurrency=self.config.scrape_concurrency,
            static_fetch_first=self.config.static_fetch_first,
            browser_fallback_only=self.config.browser_fallback_only,
            static_timeout_seconds=self.config.static_timeout_seconds,
        )
        self.candidate_store = self.candidate_store or CandidateStore(max_pool_size=self.config.max_candidate_pool)
        self.query_builder = self.query_builder or QueryBuilder(country_profiles=self.country_profiles)
        self.config = self.config.with_effective_policy()
        effective_policy = self.config.policy
        self.verifier = self.verifier or ProductIdentityVerifier(policy=effective_policy)
        self.ranker = self.ranker or ProductURLRanker(weights=self.config.score_weights, policy=effective_policy, country_profiles=self.country_profiles)
        self.selector = self.selector or FinalSelector(policy=effective_policy)
        self.enterprise_engine = self.enterprise_engine or EnterpriseEvidenceEngine()
        if (self.config.enable_llm_search_planning or self.config.enable_llm_search_feedback) and self.llm_search_planner is None:
            self.llm_search_planner = LLMSearchPlanner(config=self.config, query_builder=self.query_builder, country_profiles=self.country_profiles)
        if self.config.enable_llm_adjudication and self.llm_adjudicator is None:
            self.llm_adjudicator = ExactProductLLMAdjudicator(config=self.config)
        self.evidence_extractor = self.evidence_extractor or EvidenceExtractor()

    def run(self, product: ProductQuery, *, return_trace: bool = False) -> ProductURLMatch | HarnessTrace:
        if not product.language_code:
            profile = self.country_profiles.get(product.country_code)
            product = replace(product, language_code=profile.default_language)
        logger.info("Starting product evidence harness | row_id={} | country={} | language={} | retailer={}", product.row_id, product.country_code, product.language_code, product.retailer_name)
        budget = BudgetTracker(
            max_organic=self.config.budget.max_organic_searches,
            max_ai_mode=self.config.budget.max_ai_mode_searches,
            max_scrapes=self.config.budget.max_scrapes,
        )
        state = ProductSearchState(task=product, budget=budget)
        state.identity_graph = ProductIdentityGraphBuilder().build(product)
        executor = HarnessExecutor(
            organic_client=self.organic_client,
            ai_client=self.ai_client,
            scraper=self.scraper,
            candidate_store=self.candidate_store,
            verifier=self.verifier,
            ranker=self.ranker,
            evidence_extractor=self.evidence_extractor,
            llm_search_planner=self.llm_search_planner,
            llm_adjudicator=self.llm_adjudicator,
        )
        planner = HarnessPlanner(config=self.config, query_builder=self.query_builder, country_profiles=self.country_profiles)
        loop = BoundedHarnessLoop(config=self.config, planner=planner, executor=executor)
        state = loop.run(state)
        # Safety net: the normal path adjudicates inside the loop so failed LLM
        # judgements can trigger search repair. This fallback only runs if no
        # loop adjudication happened but promising candidates exist.
        if self.config.enable_llm_adjudication and self.llm_adjudicator is not None and not state.llm_judgements:
            state = self.llm_adjudicator.adjudicate_state(state)
        best_match = self.selector.select(
            task=product,
            scorecards=state.scorecards,
            termination_reason=state.termination_reason,
            budget_snapshot=budget.snapshot(),
            llm_calls_used=len(state.llm_call_records),
            state=state,
        )
        best_match = self._enforce_scrapable_operational_url(best_match, state)
        state.final_result = best_match
        if self.config.write_outputs:
            product_dir = ArtifactWriter(
                self.config.output_dir,
                write_markdown_reports=self.config.write_markdown_reports,
                write_trace_json=self.config.write_trace_json,
                write_debug_csvs=self.config.write_debug_csvs,
                country_profiles=self.country_profiles,
            ).write_state(state)
            self.enterprise_engine.write_artifacts(state, product_dir)
        if self.config.write_artifacts and self.config.artifact_dir:
            product_dir = ArtifactWriter(
                self.config.artifact_dir,
                include_debug_json=True,
                write_markdown_reports=True,
                write_trace_json=True,
                write_debug_csvs=True,
                country_profiles=self.country_profiles,
            ).write_state(state)
            self.enterprise_engine.write_artifacts(state, product_dir)
        logger.info("Completed harness | row_id={} | status={} | identity={} | confidence={} | url={}", product.row_id, best_match.validation_status, best_match.identity_status, best_match.confidence, best_match.product_url)
        trace = HarnessTrace(state=state, best_match=best_match)
        return trace if return_trace else best_match

    @staticmethod
    def _enforce_scrapable_operational_url(match: ProductURLMatch, state: ProductSearchState) -> ProductURLMatch:
        """Keep the submission-facing product_url scrape-safe.

        verified_exact_url is already gated by the selector. This additional gate
        prevents a weak/non-scrapable best-available candidate from being emitted
        as the operational product_url. Such URLs remain available as reference
        evidence for review instead of being submitted as usable product links.
        """
        if not match.product_url or match.verified_exact_url:
            return match

        scrape = state.scrapes.get(match.product_url)
        scrape_usable = bool(
            scrape
            and scrape.scraped
            and scrape.success
            and scrape.reachable
            and scrape.is_scrapable
            and scrape.looks_like_product_page
        )
        if scrape_usable:
            return match

        reference_url = match.best_reference_url or match.best_available_url or match.product_url
        reason = "Operational product_url cleared because selected best-available candidate was not scrape-usable product-page evidence."
        return replace(
            match,
            product_url=None,
            best_available_url=None,
            best_reference_url=reference_url,
            reference_url_status=match.reference_url_status or "REFERENCE_ONLY_NOT_SCRAPABLE_OR_UNVERIFIED",
            url_decision_status="NO_SCRAPABLE_PRODUCT_URL_FOUND",
            resolution_status="NO_SCRAPABLE_PRODUCT_URL_FOUND",
            validation_status="UNRESOLVED",
            is_exact_product_match=False,
            is_scrapable=False,
            needs_review=True,
            confidence=min(match.confidence, 0.20),
            justification=(match.justification + " | " + reason).strip(" |"),
            primary_reject_reason=match.primary_reject_reason or "NOT_SCRAPABLE_PRODUCT_PAGE",
        )


# Intentional API break from the old linear implementation. The old name is kept
# as an alias only so notebooks fail less noisily while using the new harness.
HarnessProductURLFinderPipeline = ProductEvidenceHarness
HybridProductURLFinderPipeline = ProductEvidenceHarness
