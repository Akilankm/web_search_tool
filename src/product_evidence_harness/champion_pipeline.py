from __future__ import annotations

from dataclasses import replace

from src.product_evidence_harness.constants import VALIDATION_NEEDS_REVIEW, VALIDATION_VERIFIED
from src.product_evidence_harness.contracts import HarnessTrace, ProductQuery, ProductURLMatch
from src.product_evidence_harness.tournament_artifacts import TournamentArtifactWriter
from src.product_evidence_harness.tournament_champion import ChampionContractTournamentEngine
from src.product_evidence_harness.tournament_enterprise import TournamentEnterpriseEvidenceEngine
from src.product_evidence_harness.tournament_pipeline import TournamentAwareProductEvidenceHarness
from src.product_evidence_harness.tournament_verifier import TournamentProductIdentityVerifier
from src.product_evidence_harness.url_utils import domain_of


class ChampionContractProductEvidenceHarness(TournamentAwareProductEvidenceHarness):
    def __post_init__(self) -> None:
        super().__post_init__()
        self.verifier = TournamentProductIdentityVerifier(policy=self.config.policy)
        self.tournament_engine = ChampionContractTournamentEngine(
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
        trace = super().run(product, return_trace=True)
        tournament = getattr(trace.state, "tournament_result", None)
        if self.config.tournament.enabled and tournament and tournament.champion_url:
            champion = next((c for c in trace.state.scorecards if c.candidate.url == tournament.champion_url), None)
            assessment = self.production_gate.assess_card(champion) if champion else None
            ready = bool(assessment and assessment.production_ready)
            status = assessment.status if assessment else tournament.champion_status
            reasons = "; ".join(assessment.reasons) if assessment and assessment.reasons else "champion did not pass production gate"
            old = trace.best_match
            new = replace(
                old,
                product_url=tournament.champion_url,
                best_available_url=tournament.champion_url,
                best_reference_url=tournament.runner_up_url,
                verified_exact_url=tournament.champion_url if ready else None,
                url_decision_status=status,
                resolution_status="RESOLVED" if ready else status,
                validation_status=VALIDATION_VERIFIED if ready else VALIDATION_NEEDS_REVIEW,
                is_exact_product_match=ready,
                is_scrapable=bool(champion and champion.scrape and champion.scrape.is_scrapable),
                needs_review=not ready,
                match_reason="tournament champion selected as product_url",
                justification=f"Tournament champion selected as product_url. Runner-up is supporting evidence only. Production status={status}. Reasons={reasons}.",
                selected_domain=domain_of(tournament.champion_url),
                selection_scope="tournament_champion",
                primary_reject_reason="" if ready else "TOURNAMENT_CHAMPION_NOT_PRODUCTION_READY",
            )
            trace.state.final_result = new
            self._write_outputs(trace.state, tournament)
            trace = HarnessTrace(state=trace.state, best_match=new)
        return trace if return_trace else trace.best_match

    def _write_outputs(self, state, tournament_result) -> None:
        if self.config.write_outputs:
            product_dir = TournamentArtifactWriter(self.config.output_dir, write_markdown_reports=self.config.write_markdown_reports, write_trace_json=self.config.write_trace_json, write_debug_csvs=self.config.write_debug_csvs, country_profiles=self.country_profiles).write_state(state)
            TournamentEnterpriseEvidenceEngine().write_artifacts(state, product_dir)
            self.tournament_engine.write_artifacts(tournament_result, product_dir)
        if self.config.write_artifacts and self.config.artifact_dir:
            product_dir = TournamentArtifactWriter(self.config.artifact_dir, include_debug_json=True, write_markdown_reports=True, write_trace_json=True, write_debug_csvs=True, country_profiles=self.country_profiles).write_state(state)
            TournamentEnterpriseEvidenceEngine().write_artifacts(state, product_dir)
            self.tournament_engine.write_artifacts(tournament_result, product_dir)


ProductEvidenceHarness = ChampionContractProductEvidenceHarness
HarnessProductURLFinderPipeline = ChampionContractProductEvidenceHarness
HybridProductURLFinderPipeline = ChampionContractProductEvidenceHarness
