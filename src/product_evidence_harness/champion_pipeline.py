from __future__ import annotations

from dataclasses import replace

from src.product_evidence_harness.constants import COUNTRY_ALTERNATIVE, VALIDATION_NEEDS_REVIEW, VALIDATION_VERIFIED
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
            scrape = champion.scrape if champion else None
            verification = champion.verification if champion else None
            source_types = {str(s).lower() for s in (champion.candidate.source_types if champion else ())}
            selected_from_requested = bool(champion and champion.retailer_check == "MATCHED")
            selected_from_global = bool(
                (champion and champion.country_check == COUNTRY_ALTERNATIVE)
                or "tournament_reason:global_fallback" in source_types
            )
            selection_scope = "requested_retailer" if selected_from_requested else "global_fallback" if selected_from_global else "tournament_champion"
            new = replace(
                old,
                product_url=tournament.champion_url,
                best_available_url=tournament.champion_url,
                best_reference_url=tournament.runner_up_url,
                verified_exact_url=tournament.champion_url if ready else None,
                url_decision_status=status,
                resolution_status="RESOLVED" if ready else status,
                validation_status=VALIDATION_VERIFIED if ready else VALIDATION_NEEDS_REVIEW,
                identity_status=verification.identity_status if verification else old.identity_status,
                is_exact_product_match=ready,
                is_scrapable=bool(scrape and scrape.is_scrapable),
                needs_review=not ready,
                match_reason="tournament champion selected as product_url",
                justification=f"Tournament champion selected as product_url. Runner-up is supporting evidence only. Production status={status}. Reasons={reasons}.",
                ean_check=verification.ean_check if verification else old.ean_check,
                title_check=verification.title_check if verification else old.title_check,
                quantity_check=verification.quantity_check if verification else old.quantity_check,
                page_type_check=verification.page_type_check if verification else old.page_type_check,
                retailer_check=champion.retailer_check if champion else old.retailer_check,
                country_check=champion.country_check if champion else old.country_check,
                blocking_reasons="; ".join(verification.blocking_reasons if verification else (champion.hard_failures if champion else ())),
                hard_failures=champion.hard_failures if champion else old.hard_failures,
                soft_warnings=champion.soft_warnings if champion else old.soft_warnings,
                scrape_status_code=scrape.status_code if scrape else None,
                scrape_word_count=scrape.word_count if scrape else 0,
                scrape_markdown_chars=scrape.markdown_chars if scrape else 0,
                scrape_final_url=scrape.final_url if scrape else tournament.champion_url,
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
                exact_product_check=verification.exact_product_check if verification else (champion.exact_product_check if champion else old.exact_product_check),
                variant_check=verification.variant_check if verification else (champion.variant_check if champion else old.variant_check),
                variant_conflict_terms=verification.variant_conflict_terms if verification else (),
                identity_driver=verification.identity_driver if verification else (champion.identity_driver if champion else old.identity_driver),
                ean_status=verification.ean_status if verification else old.ean_status,
                ean_conflict_is_blocking=verification.ean_conflict_is_blocking if verification else old.ean_conflict_is_blocking,
                input_ean_valid=verification.input_ean_valid if verification else old.input_ean_valid,
                input_ean_normalized=verification.input_ean_normalized if verification else old.input_ean_normalized,
                page_gtins_valid=verification.page_gtins_valid if verification else old.page_gtins_valid,
                page_gtins_ignored=verification.page_gtins_ignored if verification else old.page_gtins_ignored,
                selected_with_warning=not ready,
                primary_reject_reason="" if ready else "TOURNAMENT_CHAMPION_NOT_PRODUCTION_READY",
                confidence=max(old.confidence, champion.final_confidence if champion else 0.0),
                selected_domain=domain_of(tournament.champion_url),
                selected_retailer_name=old.retailer_name if selected_from_requested else ("global_fallback" if selected_from_global else "tournament_champion"),
                selection_scope=selection_scope,
                selected_from_requested_retailer=selected_from_requested,
                selected_from_other_country_retailer=False,
                selected_from_global_fallback=selected_from_global,
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
