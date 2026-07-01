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
from src.product_evidence_harness.production_url import ProductionURLGate
from src.product_evidence_harness.retailer_strategy import candidate_matches_requested_retailer
from src.product_evidence_harness.tournament import CandidateTournamentEngine, TournamentResult
from src.product_evidence_harness.url_utils import domain_of


@dataclass
class TournamentAwareProductEvidenceHarness(BaseProductEvidenceHarness):
    """ProductEvidenceHarness with tournament-mode orchestration.

    In tournament mode, product_url is reserved for a true champion: exact product,
    browser-openable, user-visible product content confirmed, highly scrapable,
    and rich enough for downstream product coding evidence.
    """

    tournament_engine: CandidateTournamentEngine | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        # The tournament engine uses the existing scrape/identity production gate
        # to find likely finalists quickly. The stricter browser-visible gate is
        # applied immediately after tournament discovery, before final champion
        # handoff. This avoids needing screenshot/LLM verification for every URL.
        tournament_gate = ProductionURLGate(require_user_visible_verification=False)
        self.tournament_engine = self.tournament_engine or CandidateTournamentEngine(
            config=self.config.tournament,
            query_builder=self.query_builder,
            organic_client=self.organic_client,
            candidate_store=self.candidate_store,
            scraper=self.scraper,
            verifier=self.verifier,
            ranker=self.ranker,
            evidence_extractor=self.evidence_extractor,
            production_gate=tournament_gate,
        )

    def run(self, product: ProductQuery, *, return_trace: bool = False) -> ProductURLMatch | HarnessTrace:
        if not self.config.tournament.enabled:
            return super().run(product, return_trace=return_trace)

        if not product.language_code:
            profile = self.country_profiles.get(product.country_code)
            product = replace(product, language_code=profile.default_language)

        logger.info("Starting tournament product evidence harness | row_id={} | max_serp_credits={}", product.row_id, self.config.tournament.max_serp_credits)
        budget = BudgetTracker(max_organic=self.config.tournament.max_serp_credits, max_ai_mode=0, max_scrapes=self.config.budget.max_scrapes)
        state = ProductSearchState(task=product, budget=budget)
        state.identity_graph = ProductIdentityGraphBuilder().build(product)

        tournament_result = self.tournament_engine.run(state)
        if self.config.enable_llm_adjudication and self.llm_adjudicator is not None and not state.llm_judgements:
            state = self.llm_adjudicator.adjudicate_state(state)
            state.scorecards = self.ranker.score(product=state.task, candidates=state.candidates, scrapes=state.scrapes, verifications=state.verifications)

        candidate_urls = {u for u in [tournament_result.champion_url, tournament_result.best_review_candidate_url, tournament_result.runner_up_url] if u}
        self._verify_browser_visible_content(state, candidate_urls=candidate_urls)
        tournament_result = self._apply_browser_visible_gate_to_tournament_result(state, tournament_result)
        setattr(state, "tournament_result", tournament_result)

        best_match = self.selector.select(
            task=product,
            scorecards=state.scorecards,
            termination_reason=state.termination_reason,
            budget_snapshot=budget.snapshot(),
            llm_calls_used=len(state.llm_call_records),
            state=state,
        )
        best_match = self._enforce_production_grade_product_url(best_match, state, production_gate=self.production_gate)
        best_match = self._align_final_with_tournament_result(best_match, state, tournament_result)
        state.final_result = best_match

        self._write_outputs(state, tournament_result)
        logger.info("Completed tournament harness | row_id={} | status={} | url={} | champion={}", product.row_id, best_match.url_decision_status, best_match.product_url, tournament_result.champion_url)
        trace = HarnessTrace(state=state, best_match=best_match)
        return trace if return_trace else best_match

    def _apply_browser_visible_gate_to_tournament_result(self, state: ProductSearchState, tournament_result: TournamentResult) -> TournamentResult:
        """Re-evaluate the tournament champion using the browser-visible gate."""
        champion_card, champion_assessment = self.production_gate.best_production_card(state)
        review_card = None
        review_assessment = None
        if self.tournament_engine:
            review_card, _old_review_assessment = self.tournament_engine._winner(state.scorecards)  # noqa: SLF001 - controlled internal reuse
        if review_card:
            review_assessment = self.production_gate.assess_card(review_card)
        runner_up = None
        if self.tournament_engine:
            runner_up = self.tournament_engine._runner_up(  # noqa: SLF001 - controlled internal reuse
                state.scorecards,
                champion_card.candidate.url if champion_card else review_card.candidate.url if review_card else None,
            )
        runner_score = self.production_gate.assess_card(runner_up).score if runner_up else 0.0

        confirmation = self.tournament_engine._confirm_champion(state, champion_card) if self.tournament_engine and champion_card and champion_assessment else self.tournament_engine._empty_confirmation() if self.tournament_engine else None  # noqa: SLF001
        if champion_card and champion_assessment and confirmation and not confirmation.passed:
            champion_card = None
            champion_assessment = None
        if champion_card and champion_assessment and confirmation and confirmation.passed:
            state.termination_reason = "tournament_champion_confirmed_after_browser_visible_gate"

        champion_score = champion_assessment.score if champion_assessment else 0.0
        return replace(
            tournament_result,
            champion_url=champion_card.candidate.url if champion_card else None,
            champion_score=champion_score,
            champion_status=champion_assessment.status if champion_assessment else (confirmation.status if confirmation and confirmation.attempted_count else "NO_BROWSER_VISIBLE_PRODUCTION_READY_CHAMPION"),
            champion_production_ready=bool(champion_assessment and champion_assessment.production_ready and confirmation and confirmation.passed),
            runner_up_url=runner_up.candidate.url if runner_up else None,
            champion_margin=round(champion_score - runner_score, 4) if champion_card else 0.0,
            best_review_candidate_url=review_card.candidate.url if review_card else tournament_result.best_review_candidate_url,
            best_review_candidate_score=review_assessment.score if review_assessment else tournament_result.best_review_candidate_score,
            best_review_candidate_status=review_assessment.status if review_assessment else tournament_result.best_review_candidate_status,
            champion_confirmation=confirmation,
        )

    def _align_final_with_tournament_result(self, match: ProductURLMatch, state: ProductSearchState, tournament_result: TournamentResult) -> ProductURLMatch:
        """Apply tournament result semantics to final output.

        Champion exists only when a URL passed the production gate. If no champion
        exists, product_url is cleared and the best review candidate is preserved
        as best_available_url / best_reference_url for manual investigation.
        """
        if not tournament_result.champion_url:
            review_url = tournament_result.best_review_candidate_url or match.product_url or match.best_available_url or match.best_reference_url
            justification = (
                f"No production-ready tournament champion was found. "
                f"Best review candidate={review_url or 'None'}; status={tournament_result.best_review_candidate_status}. "
                "product_url is intentionally empty because no candidate passed exact-product, browser-openable, user-visible content, highly scrapable, critical-detail evidence gates."
            )
            if match.justification:
                justification = match.justification + " | " + justification
            return replace(
                match,
                product_url=None,
                verified_exact_url=None,
                best_available_url=review_url,
                best_reference_url=review_url or match.best_reference_url,
                url_decision_status="NO_BROWSER_VISIBLE_PRODUCTION_READY_TOURNAMENT_CHAMPION",
                resolution_status="NO_BROWSER_VISIBLE_PRODUCTION_READY_TOURNAMENT_CHAMPION",
                validation_status="NEEDS_REVIEW",
                identity_status="UNVERIFIED",
                is_exact_product_match=False,
                is_scrapable=False,
                needs_review=True,
                confidence=0.0,
                match_reason="no browser-visible production-ready tournament champion",
                justification=justification,
                selected_with_warning=True,
                primary_reject_reason="NO_BROWSER_VISIBLE_PRODUCTION_READY_TOURNAMENT_CHAMPION",
                selection_scope="review_only",
                selected_retailer_name="review_only",
                selected_domain=domain_of(review_url) if review_url else "",
                selected_from_requested_retailer=False,
                selected_from_other_country_retailer=False,
                selected_from_global_fallback=False,
            )

        champion = self._card_for_url(state, tournament_result.champion_url)
        if not champion:
            return match
        assessment = self.production_gate.assess_card(champion)
        if not assessment.production_ready:
            return self._align_final_with_tournament_result(match, state, replace(tournament_result, champion_url=None))

        scrape = champion.scrape
        verification = champion.verification
        requested = bool(state.task.retailer_name and (champion.retailer_check == "MATCHED" or candidate_matches_requested_retailer(champion.candidate, state.task.retailer_name)))
        country_specific = champion.country_check in {"MATCHED", "NOT_PROVIDED"}
        global_fallback = champion.country_check == "ALTERNATIVE"
        scope = "requested_retailer" if requested else "country" if country_specific else "global_fallback" if global_fallback else "tournament_champion"
        reasons = "; ".join(assessment.reasons) if assessment.reasons else "none"
        justification = (
            f"Tournament champion selected as product_url. Champion={tournament_result.champion_url}. "
            f"Production status={assessment.status}; user_visible_status={assessment.user_visible_status}. "
            f"Runner-up={tournament_result.runner_up_url or 'None'}. Reasons={reasons}."
        )
        if match.justification:
            justification = match.justification + " | " + justification
        return replace(
            match,
            product_url=tournament_result.champion_url,
            best_available_url=tournament_result.champion_url,
            verified_exact_url=tournament_result.champion_url,
            url_decision_status=assessment.status,
            resolution_status="RESOLVED",
            validation_status="VERIFIED",
            identity_status=verification.identity_status if verification else match.identity_status,
            is_exact_product_match=True,
            needs_review=False,
            confidence=assessment.score,
            match_reason="browser-visible production-ready tournament champion selected",
            justification=justification,
            ean_check=verification.ean_check if verification else match.ean_check,
            title_check=verification.title_check if verification else match.title_check,
            quantity_check=verification.quantity_check if verification else match.quantity_check,
            page_type_check=verification.page_type_check if verification else match.page_type_check,
            retailer_check=champion.retailer_check,
            country_check=champion.country_check,
            blocking_reasons="",
            hard_failures=(),
            soft_warnings=champion.soft_warnings,
            is_scrapable=True,
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
            ean_conflict_is_blocking=False,
            input_ean_valid=verification.input_ean_valid if verification else match.input_ean_valid,
            input_ean_normalized=verification.input_ean_normalized if verification else match.input_ean_normalized,
            page_gtins_valid=verification.page_gtins_valid if verification else (),
            page_gtins_ignored=verification.page_gtins_ignored if verification else (),
            selected_with_warning=False,
            primary_reject_reason="",
            selection_scope=scope,
            selected_retailer_name=state.task.retailer_name if requested else ("global_fallback" if global_fallback else "tournament_champion"),
            selected_domain=domain_of(tournament_result.champion_url),
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
            EnterpriseEvidenceEngine().write_artifacts(state, product_dir)
            self.tournament_engine.write_artifacts(tournament_result, product_dir)


ProductEvidenceHarness = TournamentAwareProductEvidenceHarness
HarnessProductURLFinderPipeline = TournamentAwareProductEvidenceHarness
HybridProductURLFinderPipeline = TournamentAwareProductEvidenceHarness
