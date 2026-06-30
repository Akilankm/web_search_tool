from __future__ import annotations

from dataclasses import replace

from src.product_evidence_harness.elite import CodingReadiness, EnterpriseEvidenceEngine
from src.product_evidence_harness.contracts import CandidateScorecard, ProductSearchState


class TournamentEnterpriseEvidenceEngine(EnterpriseEvidenceEngine):
    """Enterprise evidence rules aligned to tournament champion semantics."""

    def coding_readiness(self, state: ProductSearchState, selected: CandidateScorecard | None) -> CodingReadiness:
        readiness = super().coding_readiness(state, selected)
        final = state.final_result
        if not final:
            return readiness
        exact_and_handoff_safe = bool(
            final.product_url
            and final.verified_exact_url
            and final.is_exact_product_match
            and not final.needs_review
        )
        if exact_and_handoff_safe:
            return readiness

        missing = list(readiness.missing_evidence)
        if "production_ready_exact_product_url" not in missing:
            missing.append("production_ready_exact_product_url")
        status = readiness.status
        if status == "CODING_READY":
            status = "CODING_PARTIAL" if readiness.score >= 0.55 else "URL_ONLY_NOT_CODING_READY"
        return replace(
            readiness,
            status=status,
            missing_evidence=tuple(missing),
            feature_hints={
                **readiness.feature_hints,
                "coding_gate_note": "Downgraded because the tournament champion is not production-ready exact product evidence.",
            },
        )

    def product_coding_input(self, state, selected, readiness, confidence, quality_tier, supporting_urls):
        payload = super().product_coding_input(state, selected, readiness, confidence, quality_tier, supporting_urls)
        final = state.final_result
        tournament = getattr(state, "tournament_result", None)
        payload["production_handoff_ready"] = bool(final and final.verified_exact_url and not final.needs_review)
        payload["tournament"] = {
            "champion_url": tournament.champion_url if tournament else None,
            "runner_up_url": tournament.runner_up_url if tournament else None,
            "champion_margin": tournament.champion_margin if tournament else None,
            "champion_status": tournament.champion_status if tournament else None,
            "search_credits_used": tournament.search_credits_used if tournament else None,
            "search_credit_limit": tournament.search_credit_limit if tournament else None,
        }
        return payload
