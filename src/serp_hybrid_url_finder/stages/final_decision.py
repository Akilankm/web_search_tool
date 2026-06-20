from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from serp_hybrid_url_finder.config import ProductURLPipelinePolicy
from serp_hybrid_url_finder.constants import (
    IDENTITY_PROBABLE,
    IDENTITY_VERIFIED,
    RETAILER_CHECK_ALTERNATIVE,
    RETAILER_CHECK_MATCHED,
    RETAILER_CHECK_NOT_PROVIDED,
    STATUS_NO_IDENTITY_MATCH,
    STATUS_NO_SCRAPABLE_CANDIDATE,
    STATUS_NO_VERIFIED_RETAILER_MATCH,
    STATUS_VERIFIED_ALTERNATIVE_MARKET_MATCH,
    STATUS_VERIFIED_MARKET_MATCH,
    STATUS_VERIFIED_RETAILER_MATCH,
    VALIDATION_NO_MATCH,
)
from serp_hybrid_url_finder.models import AIMatchEvidence, BudgetState, ProductQuery, ProductURLMatch, ScoredURLCandidate


@dataclass(frozen=True)
class FinalDecisionEngine:
    policy: ProductURLPipelinePolicy

    def decide(
        self,
        *,
        product: ProductQuery,
        scored_candidates: list[ScoredURLCandidate],
        ai_evidence: AIMatchEvidence,
        budget: BudgetState,
        repair_used: bool,
    ) -> ProductURLMatch:
        eligible = [candidate for candidate in scored_candidates if self._eligible(candidate)]
        retailer_matched = [candidate for candidate in eligible if candidate.retailer_check in {RETAILER_CHECK_MATCHED, RETAILER_CHECK_NOT_PROVIDED}]
        alternatives = [candidate for candidate in eligible if candidate.retailer_check == RETAILER_CHECK_ALTERNATIVE]

        chosen: Optional[ScoredURLCandidate] = None
        status = STATUS_NO_IDENTITY_MATCH
        failure_reason = None
        if product.retailer_name:
            if retailer_matched:
                chosen = retailer_matched[0]
                status = STATUS_VERIFIED_RETAILER_MATCH
            elif alternatives and self.policy.allow_alternative_when_retailer_given:
                chosen = alternatives[0]
                status = STATUS_VERIFIED_ALTERNATIVE_MARKET_MATCH
                failure_reason = "Requested retailer was not verified; returned best verified alternative retailer."
            elif alternatives:
                chosen = None
                status = STATUS_NO_VERIFIED_RETAILER_MATCH
                failure_reason = "Verified alternatives exist, but requested retailer is required by policy."
            else:
                chosen = None
                status = STATUS_NO_VERIFIED_RETAILER_MATCH
                failure_reason = "No verified scrapable URL was found for the requested retailer."
        else:
            if eligible:
                chosen = eligible[0]
                status = STATUS_VERIFIED_MARKET_MATCH
            else:
                chosen = None
                status = self._no_match_status(scored_candidates)
                failure_reason = "No candidate satisfied scrape + identity gates."

        best_alt = alternatives[0] if alternatives else None
        if chosen is None:
            best = scored_candidates[0] if scored_candidates else None
            return self._empty_match(
                product=product,
                ai=ai_evidence,
                budget=budget,
                repair_used=repair_used,
                status=status,
                failure_reason=failure_reason,
                best=best,
                best_alt=best_alt,
            )
        return self._from_candidate(
            product=product,
            scored=chosen,
            ai=ai_evidence,
            budget=budget,
            repair_used=repair_used,
            status=status,
            failure_reason=failure_reason,
            best_alt=best_alt if best_alt and best_alt.candidate.url != chosen.candidate.url else None,
        )

    def _eligible(self, item: ScoredURLCandidate) -> bool:
        if item.confidence < self.policy.score_policy.thresholds["minimum_final_confidence"]:
            return False
        if self.policy.require_scrapable_final and not (item.scrape and item.scrape.is_scrapable):
            return False
        if self.policy.require_identity_verified:
            if not item.verification:
                return False
            acceptable = {IDENTITY_VERIFIED}
            if self.policy.allow_probable_as_final:
                acceptable.add(IDENTITY_PROBABLE)
            if item.verification.identity_status not in acceptable:
                return False
        return True

    @staticmethod
    def _no_match_status(scored: list[ScoredURLCandidate]) -> str:
        if not scored:
            return STATUS_NO_IDENTITY_MATCH
        if not any(item.scrape and item.scrape.is_scrapable for item in scored):
            return STATUS_NO_SCRAPABLE_CANDIDATE
        return STATUS_NO_IDENTITY_MATCH

    def _from_candidate(self, *, product: ProductQuery, scored: ScoredURLCandidate, ai: AIMatchEvidence, budget: BudgetState, repair_used: bool, status: str, failure_reason: Optional[str], best_alt: Optional[ScoredURLCandidate]) -> ProductURLMatch:
        scrape = scored.scrape
        verification = scored.verification
        return ProductURLMatch(
            row_id=product.row_id,
            main_text=product.main_text,
            ean=product.ean,
            retailer_name=product.retailer_name,
            country_code=product.country_code,
            product_url=scored.candidate.url,
            confidence=scored.confidence,
            is_exact_product_match=scored.is_exact_product_match,
            match_reason=scored.reason,
            status=status,
            validation_status=scored.confidence_breakdown.validation_status if scored.confidence_breakdown else VALIDATION_NO_MATCH,
            identity_status=verification.identity_status if verification else "NONE",
            justification=scored.confidence_breakdown.justification_summary if scored.confidence_breakdown else scored.reason,
            ean_check=verification.ean_check if verification else "NONE",
            title_check=verification.title_check if verification else "NONE",
            quantity_check=verification.quantity_check if verification else "NONE",
            page_type_check=verification.page_type_check if verification else "NONE",
            retailer_check=scored.retailer_check,
            country_check=scored.country_check,
            requested_quantity=verification.requested_quantity if verification else None,
            page_quantity=verification.page_quantity if verification else None,
            blocking_reasons="; ".join(verification.blocking_reasons) if verification else "",
            best_alternative_url=best_alt.candidate.url if best_alt else None,
            best_alternative_confidence=best_alt.confidence if best_alt else 0.0,
            failure_reason=failure_reason,
            ai_match_decision=ai.match_decision,
            ai_confidence_reason=ai.confidence_reason,
            ean_evidence=ai.ean_evidence,
            title_evidence=ai.title_evidence,
            retailer_evidence=ai.retailer_evidence,
            country_evidence=ai.country_evidence,
            product_page_evidence=ai.product_page_evidence,
            organic_calls_used=budget.organic_used,
            ai_mode_calls_used=budget.ai_mode_used,
            repair_used=repair_used,
            is_scrapable=bool(scrape and scrape.is_scrapable),
            scrape_status_code=scrape.status_code if scrape else None,
            scrape_word_count=scrape.word_count if scrape else 0,
            scrape_markdown_chars=scrape.markdown_chars if scrape else 0,
            scrape_final_url=scrape.final_url if scrape else None,
            confidence_breakdown=scored.confidence_breakdown,
        )

    def _empty_match(self, *, product: ProductQuery, ai: AIMatchEvidence, budget: BudgetState, repair_used: bool, status: str, failure_reason: Optional[str], best: Optional[ScoredURLCandidate], best_alt: Optional[ScoredURLCandidate]) -> ProductURLMatch:
        scrape = best.scrape if best else None
        verification = best.verification if best else None
        return ProductURLMatch(
            row_id=product.row_id,
            main_text=product.main_text,
            ean=product.ean,
            retailer_name=product.retailer_name,
            country_code=product.country_code,
            product_url=None,
            confidence=0.0,
            is_exact_product_match=False,
            match_reason=best.reason if best else "No candidate URLs were collected.",
            status=status,
            validation_status=VALIDATION_NO_MATCH,
            identity_status=verification.identity_status if verification else "NONE",
            justification=(best.confidence_breakdown.justification_summary if best and best.confidence_breakdown else failure_reason or "No verified URL found."),
            ean_check=verification.ean_check if verification else "NONE",
            title_check=verification.title_check if verification else "NONE",
            quantity_check=verification.quantity_check if verification else "NONE",
            page_type_check=verification.page_type_check if verification else "NONE",
            retailer_check=best.retailer_check if best else "NONE",
            country_check=best.country_check if best else "NONE",
            requested_quantity=verification.requested_quantity if verification else None,
            page_quantity=verification.page_quantity if verification else None,
            blocking_reasons="; ".join(verification.blocking_reasons) if verification else "",
            best_alternative_url=best_alt.candidate.url if best_alt else None,
            best_alternative_confidence=best_alt.confidence if best_alt else 0.0,
            failure_reason=failure_reason,
            ai_match_decision=ai.match_decision,
            ai_confidence_reason=ai.confidence_reason,
            ean_evidence=ai.ean_evidence,
            title_evidence=ai.title_evidence,
            retailer_evidence=ai.retailer_evidence,
            country_evidence=ai.country_evidence,
            product_page_evidence=ai.product_page_evidence,
            organic_calls_used=budget.organic_used,
            ai_mode_calls_used=budget.ai_mode_used,
            repair_used=repair_used,
            is_scrapable=bool(scrape and scrape.is_scrapable),
            scrape_status_code=scrape.status_code if scrape else None,
            scrape_word_count=scrape.word_count if scrape else 0,
            scrape_markdown_chars=scrape.markdown_chars if scrape else 0,
            scrape_final_url=scrape.final_url if scrape else None,
            confidence_breakdown=best.confidence_breakdown if best else None,
        )
