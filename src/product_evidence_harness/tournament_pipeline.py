from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from loguru import logger

from src.product_evidence_harness.artifacts import ArtifactWriter
from src.product_evidence_harness.budget import BudgetTracker
from src.product_evidence_harness.contracts import CandidateScorecard, HarnessTrace, ProductQuery, ProductSearchState, ProductURLMatch
from src.product_evidence_harness.elite import EnterpriseEvidenceEngine
from src.product_evidence_harness.identity.graph import ProductIdentityGraphBuilder
from src.product_evidence_harness.pipeline import ProductEvidenceHarness as BaseProductEvidenceHarness
from src.product_evidence_harness.production_url import ProductionURLAssessment
from src.product_evidence_harness.retailer_strategy import candidate_matches_requested_retailer
from src.product_evidence_harness.tournament import CandidateTournamentEngine, TournamentResult
from src.product_evidence_harness.url_utils import domain_of


@dataclass
class TournamentAwareProductEvidenceHarness(BaseProductEvidenceHarness):
    """ProductEvidenceHarness with optional tournament-mode orchestration.

    When PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE=true, this class builds a broad
    candidate pool with at most PRODUCT_HARNESS_TOURNAMENT_MAX_SERP_CREDITS
    Google organic SerpAPI calls, scrapes candidates in batches, and selects the
    tournament champion as product_url. The production URL gate still decides
    whether that champion is handoff-ready. When disabled, it delegates to the
    existing loop implementation unchanged.
    """

    tournament_engine: CandidateTournamentEngine | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        self.tournament_engine = self.tournament_engine or CandidateTournamentEngine(
            config=self.config.tournament,
            query_builder=self.query_builder,
            organic_client=self.organic_client,
            candidate_store=self.candidate_store,
            scraper=self.scraper,
            verifier=self.verifier,
            ranker=self.ranker,
            evidence_extractor=self.evidence_extractor,
            production_gate=self.production_gate,
        )

    def run(self, product: ProductQuery, *, return_trace: bool = False) -> ProductURLMatch | HarnessTrace:
        if not self.config.tournament.enabled:
            return super().run(product, return_trace=return_trace)

        if not product.language_code:
            profile = self.country_profiles.get(product.country_code)
            product = replace(product, language_code=profile.default_language)

        logger.info(
            "Starting tournament product evidence harness | row_id={} | max_serp_credits={}",
            product.row_id,
            self.config.tournament.max_serp_credits,
        )
        budget = BudgetTracker(
            max_organic=self.config.tournament.max_serp_credits,
            max_ai_mode=0,
            max_scrapes=self.config.budget.max_scrapes,
        )
        state = ProductSearchState(task=product, budget=budget)
        state.identity_graph = ProductIdentityGraphBuilder().build(product)

        tournament_result = self.tournament_engine.run(state)
        if self.config.enable_llm_adjudication and self.llm_adjudicator is not None and not state.llm_judgements:
            state = self.llm_adjudicator.adjudicate_state(state)
            state.scorecards = self.ranker.score(product=state.task, candidates=state.candidates, scrapes=state.scrapes, verifications=state.verifications)

        best_match = self.selector.select(
            task=product,
            scorecards=state.scorecards,
            termination_reason=state.termination_reason,
            budget_snapshot=budget.snapshot(),
            llm_calls_used=len(state.llm_call_records),
            state=state,
        )
        best_match = self._enforce_production_grade_product_url(best_match, state, production_gate=self.production_gate)
        best_match = self._align_final_with_tournament_champion(best_match, state, tournament_result)
        state.final_result = best_match

        self._write_outputs(state, tournament_result)
        logger.info(
            "Completed tournament harness | row_id={} | status={} | url={} | tournament_champion={}",
            product.row_id,
            best_match.url_decision_status,
            best_match.product_url,
            tournament_result.champion_url,
        )
        trace = HarnessTrace(state=state, best_match=best_match)
        return trace if return_trace else best_match

    def _align_final_with_tournament_champion(self, match: ProductURLMatch, state: ProductSearchState, tournament_result: TournamentResult) -> ProductURLMatch:
        """Make the tournament champion the business-selected product_url.

        Runner-ups support the decision, but product_url must represent the champion.
        The production gate still controls needs_review and handoff readiness.
        """
        champion_url = tournament_result.champion_url
        if not champion_url:
            return match
        champion = self._card_for_url(state, champion_url)
        if not champion:
            return match
        assessment = self.production_gate.assess_card(champion)
        scrape = champion.scrape
        verification = champion.verification
        requested = bool(state.task.retailer_name and (champion.retailer_check == "MATCHED" or candidate_matches_requested_retailer(champion.candidate, state.task.retailer_name)))
        country_specific = champion.country_check in {"MATCHED", "NOT_PROVIDED"}
        global_fallback = champion.country_check == "ALTERNATIVE"
        scope = "requested_retailer" if requested else "country" if country_specific else "global_fallback" if global_fallback else "tournament_champion"
        status = assessment.status if assessment else "TOURNAMENT_CHAMPION_NOT_ASSESSED"
        production_ready = bool(assessment and assessment.production_ready)
        reasons = "; ".join(assessment.reasons) if assessment and assessment.reasons else ""
        justification = (
            f"Tournament champion selected as product_url. Champion={champion_url}. "
            f"Production status={status}. "
            f"Runner-up={tournament_result.runner_up_url or 'None'}. "
            f"Reasons={reasons or 'none'}."
        )
        if match.justification:
            justification = match.justification + " | " + justification
        return replace(
            match,
            product_url=champion_url,
            best_available_url=champion_url,
            verified_exact_url=champion_url if production_ready else None,
            url_decision_status=status,
            resolution_status="RESOLVED" if production_ready else "TOURNAMENT_CHAMPION_NEEDS_REVIEW",
            validation_status="VERIFIED" if production_ready else "NEEDS_REVIEW",
            identity_status=verification.identity_status if verification else match.identity_status,
            is_exact_product_match=bool(assessment.exact_product_match) if assessment else False,
            needs_review=not production_ready,
            confidence=assessment.score if assessment else champion.final_confidence,
            match_reason="tournament champion selected",
            justification=justification,
            ean_check=verification.ean_check if verification else match.ean_check,
            title_check=verification.title_check if verification else match.title_check,
            quantity_check=verification.quantity_check if verification else match.quantity_check,
            page_type_check=verification.page_type_check if verification else match.page_type_check,
            retailer_check=champion.retailer_check,
            country_check=champion.country_check,
            blocking_reasons="; ".join(verification.blocking_reasons if verification else champion.hard_failures),
            hard_failures=champion.hard_failures,
            soft_warnings=tuple([*champion.soft_warnings, *(('TOURNAMENT_CHAMPION_NOT_PRODUCTION_READY',) if not production_ready else ())]),
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
            exact_product_check=verification.exact_product_check if verification else champion.exact_product_check,
            variant_check=verification.variant_check if verification else champion.variant_check,
            variant_conflict_terms=verification.variant_conflict_terms if verification else (),
            identity_driver=verification.identity_driver if verification else champion.identity_driver,
            ean_status=verification.ean_status if verification else match.ean_status,
            ean_conflict_is_blocking=verification.ean_conflict_is_blocking if verification else False,
            input_ean_valid=verification.input_ean_valid if verification else match.input_ean_valid,
            input_ean_normalized=verification.input_ean_normalized if verification else match.input_ean_normalized,
            page_gtins_valid=verification.page_gtins_valid if verification else (),
            page_gtins_ignored=verification.page_gtins_ignored if verification else (),
            selected_with_warning=not production_ready,
            primary_reject_reason="" if production_ready else "TOURNAMENT_CHAMPION_NOT_PRODUCTION_READY",
            selection_scope=scope,
            selected_retailer_name=state.task.retailer_name if requested else ("global_fallback" if global_fallback else "tournament_champion"),
            selected_domain=domain_of(champion_url),
            selected_from_requested_retailer=requested,
            selected_from_other_country_retailer=bool(country_specific and state.task.retailer_name and not requested),
            selected_from_global_fallback=global_fallback,
        )

    @staticmethod
    def _card_for_url(state: ProductSearchState, url: str) -> CandidateScorecard | None:
        for card in state.scorecards:
            if card.candidate.url == url:
                return card
        return None

    def _write_outputs(self, state: ProductSearchState, tournament_result: TournamentResult) -> None:
        if self.config.write_outputs:
            product_dir = ArtifactWriter(
                self.config.output_dir,
                write_markdown_reports=self.config.write_markdown_reports,
                write_trace_json=self.config.write_trace_json,
                write_debug_csvs=self.config.write_debug_csvs,
                country_profiles=self.country_profiles,
            ).write_state(state)
            EnterpriseEvidenceEngine().write_artifacts(state, product_dir)
            self.tournament_engine.write_artifacts(tournament_result, product_dir)
        if self.config.write_artifacts and self.config.artifact_dir:
            product_dir = ArtifactWriter(
                self.config.artifact_dir,
                include_debug_json=True,
                write_markdown_reports=True,
                write_trace_json=True,
                write_debug_csvs=True,
                country_profiles=self.country_profiles,
            ).write_state(state)
            EnterpriseEvidenceEngine().write_artifacts(state, product_dir)
            self.tournament_engine.write_artifacts(tournament_result, product_dir)


ProductEvidenceHarness = TournamentAwareProductEvidenceHarness
HarnessProductURLFinderPipeline = TournamentAwareProductEvidenceHarness
HybridProductURLFinderPipeline = TournamentAwareProductEvidenceHarness
