from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

from loguru import logger

from src.product_evidence_harness.artifacts import ArtifactWriter
from src.product_evidence_harness.browser_visible import BrowserVisibleContentVerifier, BrowserVisibleVerifierConfig
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
from src.product_evidence_harness.review_artifacts import ReviewArtifactWriter
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
    browser_visible_verifier: Optional[BrowserVisibleContentVerifier] = None

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
        self.production_gate = self.production_gate or ProductionURLGate(
            require_user_visible_verification=self.config.require_browser_visible_product_content,
        )
        self.browser_visible_verifier = self.browser_visible_verifier or BrowserVisibleContentVerifier(
            BrowserVisibleVerifierConfig(
                enabled=self.config.enable_browser_visible_verification,
                capture_enabled=self.config.browser_visible_capture_enabled,
                llm_enabled=self.config.browser_visible_llm_enabled,
                top_k=self.config.browser_visible_top_k,
                timeout_ms=self.config.browser_visible_timeout_ms,
                wait_ms=self.config.browser_visible_wait_ms,
                min_token_overlap=self.config.browser_visible_min_token_overlap,
                min_title_overlap=self.config.browser_visible_min_title_overlap,
                min_llm_confidence=self.config.browser_visible_min_llm_confidence,
                image_detail=self.config.llm_image_detail,
            )
        )
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
        self._verify_browser_visible_content(state)
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
            self._write_reviewer_first_outputs(state, product_dir)
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

    def _verify_browser_visible_content(self, state: ProductSearchState, *, candidate_urls: set[str] | None = None) -> None:
        if not self.config.enable_browser_visible_verification or not self.browser_visible_verifier:
            return
        ranked = sorted(state.scorecards, key=lambda c: (c.final_confidence, c.richness_score), reverse=True)
        if candidate_urls:
            cards = [c for c in ranked if c.candidate.url in candidate_urls]
            extras = [c for c in ranked if c.candidate.url not in candidate_urls]
            cards.extend(extras[: max(0, self.config.browser_visible_top_k - len(cards))])
        else:
            cards = ranked[: max(1, self.config.browser_visible_top_k)]
        if not cards:
            return
        output_dir = Path(self.config.output_dir) / state.task.row_id / "browser_visible" if self.config.write_outputs else None
        verdicts: dict[str, dict] = dict(getattr(state, "browser_visible_verdicts", {}) or {})
        for card in cards:
            if getattr(card, "browser_visible_verdict", None):
                verdict = getattr(card, "browser_visible_verdict")
            else:
                try:
                    verdict = self.browser_visible_verifier.verify_card(state.task, card, output_dir=output_dir)
                except Exception as exc:
                    logger.warning("Browser-visible verification failed | row_id={} | url={} | error={}", state.task.row_id, card.candidate.url, exc)
                    from src.product_evidence_harness.browser_visible import BrowserVisibleProductVerdict
                    verdict = BrowserVisibleProductVerdict.failed(card.candidate.url, status="BROWSER_VISIBLE_VERIFICATION_FAILED_NEEDS_REVIEW", reason=str(exc))
                object.__setattr__(card, "browser_visible_verdict", verdict)
            verdicts[card.candidate.url] = verdict.to_dict() if hasattr(verdict, "to_dict") else dict(verdict)
        setattr(state, "browser_visible_verdicts", verdicts)

    def _write_reviewer_first_outputs(self, state: ProductSearchState, product_dir) -> None:
        """Write concise default artifacts only.

        Deep enterprise/debug artifacts are still available through
        PRODUCT_HARNESS_WRITE_ARTIFACTS / artifact_dir flows, but the default
        row folder stays reviewer-friendly.
        """
        assessment = self.enterprise_engine.assess(state)
        (product_dir / "product_coding_input.json").write_text(
            json.dumps(assessment.product_coding_input, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        if getattr(state, "browser_visible_verdicts", None):
            (product_dir / "browser_visible_verdicts.json").write_text(
                json.dumps(getattr(state, "browser_visible_verdicts"), indent=2, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
        if self.config.write_review_pack:
            ReviewArtifactWriter().write_state(product_dir, state)

    @staticmethod
    def _enforce_production_grade_product_url(match: ProductURLMatch, state: ProductSearchState, *, production_gate: ProductionURLGate | None = None) -> ProductURLMatch:
        """Prefer production-grade URLs; still keep strict non-empty fallback.

        Production-grade means the URL is browser-openable, user-visible product
        content confirmed, scrape-usable, product-page-like, rich enough for
        downstream scraping/coding, and exact product verified. This is the URL
        the browser and scraping teams should be able to use directly.
        """
        gate = production_gate or ProductionURLGate()
        production_card, production_assessment = gate.best_production_card(state)
        if production_card and production_assessment:
            promoted = ProductEvidenceHarness._replace_from_card(
                match,
                production_card,
                status=production_assessment.status,
                reason="Production-grade product URL selected: browser-openable, user-visible product content confirmed, highly scrapable, and exact-product verified.",
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
                match_reason="No URL candidate was available after search and fallback attempts.",
                justification="No product URL could be emitted because no candidate URL was discovered or retained.",
            )

        assessment = gate.assess_url_in_state(state, url)
        status = assessment.status if assessment else "PRODUCT_URL_NOT_PRODUCTION_GRADE_NEEDS_REVIEW"
        reasons = "; ".join(assessment.reasons) if assessment else "No production assessment was available."
        card = ProductEvidenceHarness._card_for_url(state, url)
        selected_warning = ProductEvidenceHarness._replace_from_card(
            match,
            card,
            status=status,
            reason=f"Best available URL retained for review only. {reasons}",
        ) if card else match
        return replace(
            selected_warning,
            product_url=url,
            best_available_url=url,
            verified_exact_url=None,
            url_decision_status=status,
            resolution_status=status,
            validation_status="NEEDS_REVIEW",
            needs_review=True,
            confidence=min(selected_warning.confidence or 0.0, 0.49),
            match_reason="best available URL retained for review; not production-grade",
            justification=f"A non-empty URL is returned for review, but it is not production-ready. Reasons: {reasons}",
            selected_with_warning=True,
            primary_reject_reason=status,
        )

    @staticmethod
    def _best_discovered_url(state: ProductSearchState) -> str | None:
        if state.scorecards:
            return sorted(state.scorecards, key=lambda c: c.final_confidence, reverse=True)[0].candidate.url
        if state.candidates:
            return state.candidates[0].url
        return None

    @staticmethod
    def _card_for_url(state: ProductSearchState, url: str) -> CandidateScorecard | None:
        for card in state.scorecards:
            if card.candidate.url == url:
                return card
        return None

    @staticmethod
    def _replace_from_card(match: ProductURLMatch, card: CandidateScorecard | None, *, status: str, reason: str) -> ProductURLMatch:
        if card is None:
            return replace(match, url_decision_status=status, resolution_status=status, justification=reason)
        scrape = card.scrape
        verification = card.verification
        url = card.candidate.url
        requested = card.retailer_check == "MATCHED"
        country_specific = card.country_check in {"MATCHED", "NOT_PROVIDED"}
        global_fallback = card.country_check == "ALTERNATIVE"
        scope = "requested_retailer" if requested else "country" if country_specific else "global_fallback" if global_fallback else "fallback"
        return replace(
            match,
            product_url=url,
            best_available_url=url,
            verified_exact_url=url if status == "PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL" else match.verified_exact_url,
            url_decision_status=status,
            resolution_status="RESOLVED" if status == "PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL" else status,
            validation_status="VERIFIED" if status == "PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL" else "NEEDS_REVIEW",
            identity_status=verification.identity_status if verification else match.identity_status,
            is_exact_product_match=bool(verification and verification.exact_product_check == "EXACT_MATCH"),
            needs_review=status != "PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL",
            confidence=card.final_confidence,
            match_reason=reason,
            justification=reason,
            ean_check=verification.ean_check if verification else match.ean_check,
            title_check=verification.title_check if verification else match.title_check,
            quantity_check=verification.quantity_check if verification else match.quantity_check,
            page_type_check=verification.page_type_check if verification else match.page_type_check,
            retailer_check=card.retailer_check,
            country_check=card.country_check,
            blocking_reasons="; ".join(verification.blocking_reasons) if verification else "",
            hard_failures=tuple(card.hard_failures),
            soft_warnings=tuple(card.soft_warnings),
            is_scrapable=bool(scrape and scrape.is_scrapable),
            scrape_status_code=scrape.status_code if scrape else None,
            scrape_word_count=scrape.word_count if scrape else 0,
            scrape_markdown_chars=scrape.markdown_chars if scrape else 0,
            scrape_final_url=scrape.final_url if scrape else None,
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
            exact_product_check=verification.exact_product_check if verification else card.exact_product_check,
            variant_check=verification.variant_check if verification else card.variant_check,
            variant_conflict_terms=verification.variant_conflict_terms if verification else (),
            identity_driver=verification.identity_driver if verification else card.identity_driver,
            ean_status=verification.ean_status if verification else match.ean_status,
            ean_conflict_is_blocking=False,
            input_ean_valid=verification.input_ean_valid if verification else match.input_ean_valid,
            input_ean_normalized=verification.input_ean_normalized if verification else match.input_ean_normalized,
            page_gtins_valid=verification.page_gtins_valid if verification else (),
            page_gtins_ignored=verification.page_gtins_ignored if verification else (),
            selected_with_warning=status != "PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL",
            primary_reject_reason=card.primary_reject_reason if status != "PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL" else "",
            selection_scope=scope,
            selected_retailer_name=card.candidate.domain,
            selected_domain=domain_of(url),
            selected_from_requested_retailer=requested,
            selected_from_other_country_retailer=bool(country_specific and not requested),
            selected_from_global_fallback=global_fallback,
        )
