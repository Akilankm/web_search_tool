from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

from loguru import logger

from src.product_evidence_harness.artifacts import ArtifactWriter
from src.product_evidence_harness.budget import BudgetTracker
from src.product_evidence_harness.candidate_store import CandidateStore
from src.product_evidence_harness.config import HarnessConfig, SerpAPIConfig
from src.product_evidence_harness.contracts import CandidateScorecard, HarnessTrace, ProductQuery, ProductSearchState, ProductURLMatch
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
from src.product_evidence_harness.production_url import ProductionURLGate
from src.product_evidence_harness.query_builder import QueryBuilder
from src.product_evidence_harness.ranker import ProductURLRanker
from src.product_evidence_harness.scraper import CrawlScraper
from src.product_evidence_harness.selector import FinalSelector
from src.product_evidence_harness.serp_clients import GoogleAIModeClient, GoogleOrganicSearchClient
from src.product_evidence_harness.url_utils import domain_of


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
    production_gate: Optional[ProductionURLGate] = None

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
        self.production_gate = self.production_gate or ProductionURLGate()
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
        best_match = self._enforce_production_grade_product_url(best_match, state, production_gate=self.production_gate)
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
    def _enforce_production_grade_product_url(match: ProductURLMatch, state: ProductSearchState, *, production_gate: ProductionURLGate | None = None) -> ProductURLMatch:
        """Prefer production-grade URLs; still keep strict non-empty fallback.

        Production-grade means the URL is browser-openable, scrape-usable,
        product-page-like, rich enough for downstream scraping/coding, and exact
        product verified. This is the URL the browser and scraping teams should
        be able to use directly.

        If no production-grade URL exists, product_url is still filled with the
        best discovered URL per the non-empty business rule, but it is marked
        review-only/non-production through status fields.
        """
        gate = production_gate or ProductionURLGate()
        production_card, production_assessment = gate.best_production_card(state)
        if production_card and production_assessment:
            promoted = ProductEvidenceHarness._replace_from_card(
                match,
                production_card,
                status=production_assessment.status,
                reason="Production-grade product URL selected: browser-openable, highly scrapable, and exact-product verified.",
            )
            return promoted

        url = (
            match.product_url
            or match.verified_exact_url
            or match.best_available_url
            or match.best_reference_url
            or ProductEvidenceHarness._best_discovered_url(state)
        )
        if not url:
            return replace(
                match,
                url_decision_status="STRICT_PRODUCT_URL_REQUIRED_BUT_NO_URL_CANDIDATE_AVAILABLE",
                resolution_status="STRICT_PRODUCT_URL_REQUIRED_BUT_NO_URL_CANDIDATE_AVAILABLE",
                validation_status="UNRESOLVED",
                needs_review=True,
                confidence=0.0,
                primary_reject_reason=match.primary_reject_reason or "NO_URL_CANDIDATE_AVAILABLE",
                justification=(match.justification + " | Strict product_url policy could not be satisfied because no URL candidate was discovered by any search/scrape source.").strip(" |"),
            )

        assessment = gate.assess_url_in_state(state, url)
        if assessment and assessment.production_ready:
            # Defensive path for cases where the current selected URL is already
            # production-ready but not returned by best_production_card because of
            # missing scorecard ordering context.
            return replace(
                match,
                product_url=url,
                best_available_url=match.best_available_url or url,
                verified_exact_url=match.verified_exact_url or url,
                url_decision_status=assessment.status,
                resolution_status="RESOLVED",
                validation_status="VERIFIED",
                is_exact_product_match=True,
                is_scrapable=True,
                needs_review=False,
                confidence=max(match.confidence, assessment.score),
                primary_reject_reason="",
                justification=(match.justification + " | Production-grade product URL confirmed.").strip(" |"),
            )

        scrape = state.scrapes.get(url)
        scrape_usable = bool(
            scrape
            and scrape.scraped
            and scrape.success
            and scrape.reachable
            and scrape.is_scrapable
            and scrape.looks_like_product_page
        )
        status = assessment.status if assessment else ProductEvidenceHarness._strict_url_status(url, state, scrape_usable=scrape_usable)
        reasons = "; ".join(assessment.reasons) if assessment and assessment.reasons else "production-grade checks failed"
        reason = (
            "No production-grade exact/scrapable/browser-openable URL passed all final gates. "
            "Strict non-empty product_url policy emitted the best discovered fallback URL for review. "
            f"Production gate reasons: {reasons}."
        )
        return replace(
            match,
            product_url=url,
            best_available_url=match.best_available_url or url,
            best_reference_url=match.best_reference_url or url,
            reference_url_status=match.reference_url_status or status,
            url_decision_status=status,
            resolution_status=status,
            validation_status="NEEDS_REVIEW",
            is_exact_product_match=False,
            is_scrapable=scrape_usable,
            needs_review=True,
            confidence=min(match.confidence if match.confidence else 0.25, 0.70 if scrape_usable else 0.35),
            justification=(match.justification + " | " + reason).strip(" |"),
            primary_reject_reason=match.primary_reject_reason or "PRODUCT_URL_NOT_PRODUCTION_GRADE",
        )

    @staticmethod
    def _replace_from_card(match: ProductURLMatch, card: CandidateScorecard, *, status: str, reason: str) -> ProductURLMatch:
        scrape = card.scrape
        verification = card.verification
        url = card.candidate.url
        country_specific = card.country_check in {"MATCHED", "NOT_PROVIDED"}
        global_fallback = card.country_check == "COUNTRY_ALTERNATIVE"
        return replace(
            match,
            product_url=url,
            best_available_url=url,
            verified_exact_url=url,
            url_decision_status=status,
            resolution_status="RESOLVED",
            validation_status="VERIFIED",
            identity_status=verification.identity_status if verification else "VERIFIED",
            is_exact_product_match=True,
            match_reason="production-grade exact product URL selected",
            justification=(match.justification + " | " + reason).strip(" |"),
            ean_check=verification.ean_check if verification else match.ean_check,
            title_check=verification.title_check if verification else match.title_check,
            quantity_check=verification.quantity_check if verification else match.quantity_check,
            page_type_check=verification.page_type_check if verification else match.page_type_check,
            retailer_check=card.retailer_check,
            country_check=card.country_check,
            requested_quantity=verification.requested_quantity if verification else match.requested_quantity,
            page_quantity=verification.page_quantity if verification else match.page_quantity,
            blocking_reasons="",
            hard_failures=(),
            soft_warnings=card.soft_warnings,
            is_scrapable=True,
            scrape_status_code=scrape.status_code if scrape else None,
            scrape_word_count=scrape.word_count if scrape else 0,
            scrape_markdown_chars=scrape.markdown_chars if scrape else 0,
            scrape_final_url=scrape.final_url if scrape else url,
            richness_score=scrape.richness_score if scrape else 0.0,
            price=scrape.price if scrape else None,
            currency=scrape.currency if scrape else "",
            brand=scrape.brand if scrape else "",
            manufacturer=scrape.manufacturer if scrape else "",
            description=scrape.description if scrape else "",
            specs_count=len(scrape.specs) if scrape else 0,
            image_count=scrape.image_count if scrape else 0,
            specs=dict(scrape.specs) if scrape else {},
            image_urls=tuple(scrape.image_urls) if scrape else (),
            exact_product_check=verification.exact_product_check if verification else "EXACT_MATCH",
            variant_check=verification.variant_check if verification else "MATCHED",
            variant_conflict_terms=verification.variant_conflict_terms if verification else (),
            identity_driver=verification.identity_driver if verification else card.identity_driver,
            ean_status=verification.ean_status if verification else match.ean_status,
            ean_conflict_is_blocking=False,
            input_ean_valid=verification.input_ean_valid if verification else match.input_ean_valid,
            input_ean_normalized=verification.input_ean_normalized if verification else match.input_ean_normalized,
            page_gtins_valid=verification.page_gtins_valid if verification else (),
            page_gtins_ignored=verification.page_gtins_ignored if verification else (),
            selected_with_warning=False,
            primary_reject_reason="",
            llm_used=card.llm_used,
            llm_decision=card.llm_decision,
            llm_confidence=card.llm_confidence,
            llm_exact_product_match=card.llm_exact_product_match,
            llm_reject_reason=card.llm_reject_reason,
            llm_justification=card.llm_justification,
            best_reference_url=match.best_reference_url,
            reference_url_status=match.reference_url_status,
            selection_scope="requested_retailer" if card.retailer_check == "MATCHED" else ("global_fallback" if global_fallback else "country"),
            selected_retailer_name=match.requested_retailer_name if card.retailer_check == "MATCHED" else ("global_fallback" if global_fallback else "alternative_country_retailer"),
            selected_domain=domain_of(url),
            selected_from_requested_retailer=card.retailer_check == "MATCHED",
            selected_from_other_country_retailer=bool(country_specific and card.retailer_check != "MATCHED" and match.retailer_name),
            selected_from_global_fallback=global_fallback,
            needs_review=False,
            confidence=max(match.confidence, card.final_confidence),
        )

    @staticmethod
    def _strict_url_status(url: str, state: ProductSearchState, *, scrape_usable: bool) -> str:
        if scrape_usable:
            return "BEST_AVAILABLE_PRODUCT_URL_NEEDS_REVIEW"
        scrape = state.scrapes.get(url)
        if scrape and scrape.scraped:
            if scrape.looks_like_product_page:
                return "BEST_AVAILABLE_PRODUCT_URL_NOT_SCRAPABLE_NEEDS_REVIEW"
            return "BEST_AVAILABLE_URL_NOT_CONFIRMED_PRODUCT_PAGE_NEEDS_REVIEW"
        if any(c.url == url for c in state.candidates):
            return "DISCOVERED_CANDIDATE_URL_UNSCRAPED_NEEDS_REVIEW"
        return "REFERENCE_URL_FROM_SEARCH_NEEDS_REVIEW"

    @staticmethod
    def _best_discovered_url(state: ProductSearchState) -> Optional[str]:
        for card in state.scorecards:
            if card.candidate.url:
                return card.candidate.url
        for candidate in state.candidates:
            if candidate.url:
                return candidate.url
        for url in state.scrapes:
            if url:
                return url
        for response in state.organic_responses:
            for result in response.results:
                if result.url:
                    return result.url
        for response in state.ai_responses:
            for reference in response.references:
                if reference.link:
                    return reference.link
        return None


# Intentional API break from the old linear implementation. The old name is kept
# as an alias only so notebooks fail less noisily while using the new harness.
HarnessProductURLFinderPipeline = ProductEvidenceHarness
HybridProductURLFinderPipeline = ProductEvidenceHarness
