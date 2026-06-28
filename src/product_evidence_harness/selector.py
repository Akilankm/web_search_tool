from __future__ import annotations

from dataclasses import dataclass

from src.product_evidence_harness.config import HarnessPolicy
from src.product_evidence_harness.constants import (
    COUNTRY_ALTERNATIVE,
    COUNTRY_MATCHED,
    COUNTRY_NOT_PROVIDED,
    IDENTITY_UNVERIFIED,
    IDENTITY_VERIFIED,
    RETAILER_NOT_PROVIDED,
    VALIDATION_NEEDS_REVIEW,
    VALIDATION_REJECTED,
    VALIDATION_UNRESOLVED,
    VALIDATION_VERIFIED,
)
from src.product_evidence_harness.contracts import CandidateScorecard, ProductQuery, ProductSearchState, ProductURLMatch
from src.product_evidence_harness.retailer_strategy import candidate_matches_requested_retailer, requested_retailer_metrics
from src.product_evidence_harness.url_utils import domain_of


@dataclass(frozen=True)
class FinalSelector:
    policy: HarnessPolicy = HarnessPolicy()

    def select(self, *, task: ProductQuery, scorecards: list[CandidateScorecard], termination_reason: str | None, budget_snapshot, llm_calls_used: int = 0, state: ProductSearchState | None = None) -> ProductURLMatch:
        rr_metrics = requested_retailer_metrics(
            state,
            min_scrapes_for_escape=self.policy.requested_retailer_min_scrapes_for_escape,
            min_richness_for_evidence=self.policy.requested_retailer_min_richness_for_evidence,
        ) if state is not None else requested_retailer_metrics(
            ProductSearchState(task=task, budget=None, scorecards=scorecards),
            min_scrapes_for_escape=self.policy.requested_retailer_min_scrapes_for_escape,
            min_richness_for_evidence=self.policy.requested_retailer_min_richness_for_evidence,
        )
        exact = self._select_exact_card(scorecards)
        best_available = self._select_best_available_card(scorecards, allow_hard_rejected=False)
        best_reference = self._select_best_available_card(scorecards, allow_hard_rejected=True)
        selected = exact or best_available or (best_reference if self.policy.return_rejected_reference_as_product_url else None)
        if not selected:
            return ProductURLMatch(
                row_id=task.row_id,
                main_text=task.main_text,
                country_code=task.country_code,
                retailer_name=task.retailer_name,
                ean=task.ean,
                product_url=None,
                best_available_url=None,
                verified_exact_url=None,
                url_decision_status="NO_ACCEPTABLE_URL_FOUND" if best_reference else "NO_CANDIDATE_FOUND",
                confidence=0.0,
                validation_status=VALIDATION_UNRESOLVED,
                identity_status=IDENTITY_UNVERIFIED,
                is_exact_product_match=False,
                match_reason="No acceptable product URL was found" if best_reference else "No URL candidate was found",
                justification=("Candidate URLs were discovered, but all usable references were hard-rejected or too weak; see best_reference_url/candidates.csv." if best_reference else "No candidate URL could be discovered within the configured search budget."),
                termination_reason=termination_reason,
                organic_calls_used=budget_snapshot.organic_used,
                ai_mode_calls_used=budget_snapshot.ai_mode_used,
                scrape_calls_used=budget_snapshot.scrape_used,
                resolution_status="NO_ACCEPTABLE_URL_FOUND" if best_reference else "NO_CANDIDATE_FOUND",
                availability_inference="UNKNOWN",
                exact_product_check="UNKNOWN",
                variant_check="UNKNOWN",
                identity_driver="NO_CANDIDATE_FOUND",
                primary_reject_reason="NO_CANDIDATE_FOUND",
                llm_calls_used=llm_calls_used,
                needs_review=True,
                best_reference_url=best_reference.candidate.url if best_reference else None,
                reference_url_status="REFERENCE_ONLY_REJECTED_OR_WEAK" if best_reference else "",
                input_validation_status="WARN" if task.input_validation_warnings else "OK",
                input_validation_warnings=task.input_validation_warnings,
                **rr_metrics.to_dict(),
            )

        is_exact = exact is not None and selected.candidate.url == exact.candidate.url
        reference_only = best_reference is not None and selected is not best_reference and not is_exact
        scrape = selected.scrape
        verification = selected.verification
        final_status = selected.validation_status if is_exact else VALIDATION_NEEDS_REVIEW
        if final_status == VALIDATION_REJECTED:
            final_status = VALIDATION_NEEDS_REVIEW

        reasons = list(selected.ranking_reasons)
        if selected.llm_used:
            reasons.append(f"llm_decision={selected.llm_decision}")
            if selected.llm_justification:
                reasons.append("llm_justification=" + selected.llm_justification[:500])
        if selected.hard_failures:
            reasons.append("hard_failures=" + "; ".join(selected.hard_failures))
        if selected.soft_warnings:
            reasons.append("warnings=" + "; ".join(selected.soft_warnings))
        if not is_exact:
            reasons.append("best_available_url_returned_because_no_verified_exact_url_passed_all_final_gates")
        justification = " | ".join(reasons) or selected.candidate.evidence_text()[:500]

        country_specific = selected.country_check in {COUNTRY_MATCHED, COUNTRY_NOT_PROVIDED}
        global_fallback = selected.country_check == COUNTRY_ALTERNATIVE
        selected_from_requested = bool(task.retailer_name and candidate_matches_requested_retailer(selected.candidate, task.retailer_name))
        selected_from_other_country = bool(country_specific and task.retailer_name and not selected_from_requested)
        selection_scope = self._selection_scope(is_exact=is_exact, selected_from_requested=selected_from_requested, selected_from_other_country=selected_from_other_country, global_fallback=global_fallback)
        decision_status = self._decision_status(selected, is_exact=is_exact, country_specific=country_specific, global_fallback=global_fallback, selected_from_requested=selected_from_requested, selected_from_other_country=selected_from_other_country)

        return ProductURLMatch(
            row_id=task.row_id,
            main_text=task.main_text,
            country_code=task.country_code,
            retailer_name=task.retailer_name,
            ean=task.ean,
            product_url=selected.candidate.url,
            best_available_url=selected.candidate.url,
            verified_exact_url=selected.candidate.url if is_exact else None,
            url_decision_status=decision_status,
            is_country_specific=country_specific,
            is_global_fallback=global_fallback,
            needs_review=not is_exact,
            confidence=selected.final_confidence,
            validation_status=final_status,
            identity_status=verification.identity_status if verification else IDENTITY_UNVERIFIED,
            is_exact_product_match=is_exact,
            match_reason="; ".join(selected.ranking_reasons[:5]),
            justification=justification,
            ean_check=verification.ean_check if verification else "UNKNOWN",
            title_check=verification.title_check if verification else "UNKNOWN",
            quantity_check=verification.quantity_check if verification else "UNKNOWN",
            page_type_check=verification.page_type_check if verification else "UNKNOWN",
            retailer_check=selected.retailer_check,
            country_check=selected.country_check,
            requested_quantity=verification.requested_quantity if verification else None,
            page_quantity=verification.page_quantity if verification else None,
            blocking_reasons="; ".join(verification.blocking_reasons if verification else selected.hard_failures),
            hard_failures=selected.hard_failures,
            soft_warnings=selected.soft_warnings,
            termination_reason=termination_reason,
            organic_calls_used=budget_snapshot.organic_used,
            ai_mode_calls_used=budget_snapshot.ai_mode_used,
            scrape_calls_used=budget_snapshot.scrape_used,
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
            resolution_status="RESOLVED" if is_exact else "BEST_AVAILABLE_NOT_VERIFIED",
            availability_inference="UNKNOWN",
            exact_product_check=verification.exact_product_check if verification else "UNKNOWN",
            variant_check=verification.variant_check if verification else "UNKNOWN",
            variant_conflict_terms=verification.variant_conflict_terms if verification else (),
            identity_driver=verification.identity_driver if verification else "UNKNOWN",
            ean_status=verification.ean_status if verification else "UNKNOWN",
            ean_conflict_is_blocking=verification.ean_conflict_is_blocking if verification else False,
            input_ean_valid=verification.input_ean_valid if verification else None,
            input_ean_normalized=verification.input_ean_normalized if verification else None,
            page_gtins_valid=verification.page_gtins_valid if verification else (),
            page_gtins_ignored=verification.page_gtins_ignored if verification else (),
            selected_with_warning=selected.selected_with_warning,
            primary_reject_reason=selected.primary_reject_reason,
            llm_used=selected.llm_used,
            llm_decision=selected.llm_decision,
            llm_confidence=selected.llm_confidence,
            llm_exact_product_match=selected.llm_exact_product_match,
            llm_reject_reason=selected.llm_reject_reason,
            llm_justification=selected.llm_justification,
            llm_calls_used=llm_calls_used,
            best_reference_url=best_reference.candidate.url if best_reference else None,
            reference_url_status=("REFERENCE_ONLY_REJECTED_OR_WEAK" if best_reference and best_reference.hard_failures else ""),
            input_validation_status="WARN" if task.input_validation_warnings else "OK",
            input_validation_warnings=task.input_validation_warnings,
            **rr_metrics.to_dict(),
            selection_scope=selection_scope,
            selected_retailer_name=(task.retailer_name if selected_from_requested else ("alternative_country_retailer" if selected_from_other_country else ("global_fallback" if global_fallback else ""))),
            selected_domain=domain_of(selected.candidate.url),
            selected_from_requested_retailer=selected_from_requested,
            selected_from_other_country_retailer=selected_from_other_country,
            selected_from_global_fallback=global_fallback,
        )

    def _is_final_usable(self, card: CandidateScorecard) -> bool:
        scrape = card.scrape
        verification = card.verification
        if not scrape or not verification:
            return False
        if not (scrape.scraped and scrape.success and scrape.reachable and scrape.is_scrapable):
            return False
        if not scrape.looks_like_product_page:
            return False
        if card.hard_failures:
            return False
        if verification.identity_status != IDENTITY_VERIFIED:
            return False
        if verification.exact_product_check not in {"EXACT_MATCH", "UNKNOWN"}:
            return False
        if verification.variant_check == "CONFLICT":
            return False
        if self.policy.require_llm_exact_match_for_final:
            if not card.llm_used:
                return False
            if card.llm_decision not in {"EXACT_MATCH", "EXACT_MATCH_WITH_WARNING"}:
                return False
            if not card.llm_exact_product_match:
                return False
        return True

    def _select_exact_card(self, scorecards: list[CandidateScorecard]) -> CandidateScorecard | None:
        country_cards = [card for card in scorecards if card.country_check in {COUNTRY_MATCHED, COUNTRY_NOT_PROVIDED}]
        global_cards = [card for card in scorecards if card.country_check == COUNTRY_ALTERNATIVE]
        for card in country_cards:
            if card.validation_status == VALIDATION_VERIFIED and self._is_final_usable(card):
                return card
        if self.policy.allow_global_fallback:
            for card in global_cards:
                if card.validation_status == VALIDATION_VERIFIED and self._is_final_usable(card):
                    return card
        for card in scorecards:
            if self._is_final_usable(card):
                return card
        return None

    def _select_best_available_card(self, scorecards: list[CandidateScorecard], *, allow_hard_rejected: bool = False) -> CandidateScorecard | None:
        if not scorecards:
            return None
        candidates = list(scorecards) if allow_hard_rejected else [c for c in scorecards if not c.hard_failures]
        if not candidates:
            return None
        def usable_rank(card: CandidateScorecard) -> tuple[float, ...]:
            s = card.scrape
            country = 1 if card.country_check in {COUNTRY_MATCHED, COUNTRY_NOT_PROVIDED} else 0
            scraped = 1 if s and s.scraped and s.reachable else 0
            scrapable = 1 if s and s.is_scrapable else 0
            product_page = 1 if s and s.looks_like_product_page else 0
            no_hard = 1 if not card.hard_failures else 0
            llm_exact = 1 if card.llm_decision in {"EXACT_MATCH", "EXACT_MATCH_WITH_WARNING"} else 0
            return (llm_exact, no_hard, country, scrapable, product_page, scraped, card.richness_score, card.final_confidence)
        return sorted(candidates, key=usable_rank, reverse=True)[0]

    @staticmethod
    def _selection_scope(*, is_exact: bool, selected_from_requested: bool, selected_from_other_country: bool, global_fallback: bool) -> str:
        if selected_from_requested:
            return "requested_retailer"
        if selected_from_other_country:
            return "country_alternative_retailer"
        if global_fallback:
            return "global_fallback"
        return "country" if is_exact else "best_available"

    @staticmethod
    def _decision_status(card: CandidateScorecard, *, is_exact: bool, country_specific: bool, global_fallback: bool, selected_from_requested: bool = False, selected_from_other_country: bool = False) -> str:
        if is_exact and selected_from_requested:
            return "EXACT_REQUESTED_RETAILER_MATCH"
        if is_exact and selected_from_other_country:
            return "EXACT_COUNTRY_ALTERNATIVE_RETAILER_MATCH"
        if is_exact and country_specific:
            return "EXACT_COUNTRY_MATCH"
        if is_exact and global_fallback:
            return "EXACT_GLOBAL_FALLBACK"
        if card.scrape and not card.scrape.is_scrapable:
            return "BEST_AVAILABLE_NOT_SCRAPABLE"
        if card.hard_failures:
            return "BEST_AVAILABLE_REJECTED_NEEDS_REVIEW"
        if selected_from_other_country:
            return "BEST_AVAILABLE_COUNTRY_ALTERNATIVE_NEEDS_REVIEW"
        if global_fallback:
            return "BEST_AVAILABLE_GLOBAL_NEEDS_REVIEW"
        return "BEST_AVAILABLE_NEEDS_REVIEW"
