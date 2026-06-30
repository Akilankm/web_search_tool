from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from loguru import logger

from src.product_evidence_harness.artifacts import ArtifactWriter
from src.product_evidence_harness.budget import BudgetTracker
from src.product_evidence_harness.contracts import HarnessTrace, ProductQuery, ProductSearchState, ProductURLMatch
from src.product_evidence_harness.elite import EnterpriseEvidenceEngine
from src.product_evidence_harness.identity.graph import ProductIdentityGraphBuilder
from src.product_evidence_harness.pipeline import ProductEvidenceHarness as BaseProductEvidenceHarness
from src.product_evidence_harness.tournament import CandidateTournamentEngine, TournamentResult


@dataclass
class TournamentAwareProductEvidenceHarness(BaseProductEvidenceHarness):
    """ProductEvidenceHarness with optional tournament-mode orchestration.

    When PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE=true, this class builds a broad
    candidate pool with at most PRODUCT_HARNESS_TOURNAMENT_MAX_SERP_CREDITS
    Google organic SerpAPI calls, scrapes candidates in batches, and lets the
    production URL gate promote the champion. When disabled, it delegates to the
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
