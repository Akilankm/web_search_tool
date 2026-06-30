from __future__ import annotations

from typing import Any

from src.product_evidence_harness.artifacts import ArtifactWriter
from src.product_evidence_harness.contracts import CandidateScorecard, ProductSearchState


class TournamentArtifactWriter(ArtifactWriter):
    """Artifact writer that makes the tournament champion contract explicit."""

    def final_submission_row(self, state: ProductSearchState, *, product_dir=None) -> dict[str, Any]:
        row = super().final_submission_row(state, product_dir=product_dir)
        tournament = getattr(state, "tournament_result", None)
        row.update({
            "tournament_champion_url": tournament.champion_url if tournament else None,
            "tournament_runner_up_url": tournament.runner_up_url if tournament else None,
            "tournament_champion_status": tournament.champion_status if tournament else None,
            "tournament_champion_score": tournament.champion_score if tournament else None,
            "tournament_champion_margin": tournament.champion_margin if tournament else None,
            "tournament_search_credits_used": tournament.search_credits_used if tournament else None,
            "tournament_search_credit_limit": tournament.search_credit_limit if tournament else None,
            "product_url_is_tournament_champion": bool(tournament and row.get("product_url") == tournament.champion_url),
            "llm_calls_attempted": len(state.llm_call_records),
            "llm_calls_successful": sum(1 for r in state.llm_call_records if r.success),
            "llm_calls_failed": sum(1 for r in state.llm_call_records if not r.success),
            "llm_candidates_judged": len(state.llm_judgements),
        })
        return row

    def _final_decision_bullets(self, state: ProductSearchState) -> list[str]:
        lines = super()._final_decision_bullets(state)
        tournament = getattr(state, "tournament_result", None)
        if tournament:
            lines.insert(0, f"- **Tournament champion URL:** {self._md_link(tournament.champion_url)}")
            lines.insert(1, f"- **Tournament runner-up URL:** {self._md_link(tournament.runner_up_url)}")
            lines.insert(2, f"- **Champion margin:** `{tournament.champion_margin}`")
            lines.insert(3, f"- **Champion production status:** `{tournament.champion_status}`")
            lines.insert(4, "- **Contract:** `product_url is the tournament champion; runner-ups are supporting evidence only.`")
        return lines

    def _candidate_table_markdown(self, state: ProductSearchState, *, limit: int) -> str:
        cards = self._ranked_cards(state)[:limit]
        lines = [
            "| Rank | Candidate ID | Role | Scope | URL | Scraped | Product page | Exactness | Variant | Confidence | Decision / reject reason |",
            "|---:|---|---|---|---|---|---|---|---|---:|---|",
        ]
        if not cards:
            lines.append("| - | - | - | - | No candidates | - | - | - | - | - | - |")
            return "\n".join(lines)
        for idx, card in enumerate(cards, start=1):
            s = card.scrape
            v = card.verification
            role = self._candidate_role(state, card)
            scope = self._candidate_scope(state, card)
            exactness = v.exact_product_check if v else card.exact_product_check or "UNKNOWN"
            variant = v.variant_check if v else card.variant_check or "UNKNOWN"
            reason = self._candidate_reason(state, card, role)
            lines.append(
                f"| {idx} | `CAND-{idx:03d}` | `{role}` | `{scope}` | {self._md_link(card.candidate.url)} | `{bool(s and s.is_scrapable)}` | `{bool(s and s.looks_like_product_page)}` | `{exactness}` | `{variant}` | {card.final_confidence:.3f} | {self._md_cell(reason)} |"
            )
        return "\n".join(lines)

    def _candidate_detail_markdown(self, state: ProductSearchState, card: CandidateScorecard, *, rank: int) -> list[str]:
        s = card.scrape
        v = card.verification
        role = self._candidate_role(state, card)
        return [
            f"- **Candidate ID:** `CAND-{rank:03d}`",
            f"- **Tournament role:** `{role}`",
            f"- **URL:** {self._md_link(card.candidate.url)}",
            f"- **Domain:** `{card.candidate.domain}`",
            f"- **Scope:** `{self._candidate_scope(state, card)}`",
            f"- **Title:** {self._md_text(card.candidate.title)}",
            f"- **Confidence:** `{card.final_confidence:.3f}`",
            f"- **Validation status:** `{card.validation_status}`",
            f"- **Identity status:** `{v.identity_status if v else 'UNVERIFIED'}`",
            f"- **Exact product check:** `{v.exact_product_check if v else 'UNKNOWN'}`",
            f"- **Variant check:** `{v.variant_check if v else 'UNKNOWN'}`",
            f"- **Scrapable:** `{bool(s and s.is_scrapable)}`",
            f"- **Product page:** `{bool(s and s.looks_like_product_page)}`",
            f"- **Richness score:** `{s.richness_score if s else 0:.3f}`",
            f"- **Decision reason:** {self._md_text(self._candidate_reason(state, card, role))}",
        ]

    def _rejection_summary_markdown(self, state: ProductSearchState) -> str:
        cards = self._ranked_cards(state)
        lines = ["| Candidate | Role | URL | Reason |", "|---|---|---|---|"]
        for card in cards[:30]:
            role = self._candidate_role(state, card)
            if role in {"TOURNAMENT_CHAMPION_PRODUCTION_READY", "TOURNAMENT_CHAMPION_REVIEW_ONLY"}:
                continue
            rank = self._card_rank(state, card)
            lines.append(f"| `CAND-{rank:03d}` | `{role}` | {self._md_link(card.candidate.url)} | {self._md_cell(self._candidate_reason(state, card, role))} |")
        if len(lines) == 2:
            lines.append("| - | - | No rejected/supporting candidates | - |")
        return "\n".join(lines)

    def _candidate_trace_row(self, state: ProductSearchState, card: CandidateScorecard, rank: int) -> dict[str, Any]:
        row = super()._candidate_trace_row(state, card, rank)
        role = self._candidate_role(state, card)
        row["tournament_role"] = role
        row["decision_reason"] = self._candidate_reason(state, card, role)
        return row

    def _candidate_scope(self, state: ProductSearchState, card: CandidateScorecard) -> str:
        source_types = {str(s).lower() for s in card.candidate.source_types or ()}
        for prefix, label in (
            ("tournament_reason:requested_retailer", "REQUESTED_RETAILER"),
            ("tournament_reason:ean_country", "EAN_COUNTRY_SEARCH"),
            ("tournament_reason:country_alternatives", "COUNTRY_ALTERNATIVE"),
            ("tournament_reason:secondary_language", "SECONDARY_LANGUAGE_COUNTRY_SEARCH"),
            ("tournament_reason:global_fallback", "GLOBAL_FALLBACK"),
        ):
            if prefix in source_types:
                return label
        return super()._candidate_scope(state, card)

    def _candidate_role(self, state: ProductSearchState, card: CandidateScorecard) -> str:
        final = state.final_result
        tournament = getattr(state, "tournament_result", None)
        url = card.candidate.url
        if tournament and url == tournament.champion_url:
            return "TOURNAMENT_CHAMPION_PRODUCTION_READY" if final and not final.needs_review else "TOURNAMENT_CHAMPION_REVIEW_ONLY"
        if tournament and url == tournament.runner_up_url:
            return "RUNNER_UP_SUPPORTING_EVIDENCE"
        if card.hard_failures:
            return "REJECTED_HARD_FAILURE"
        if not card.scrape:
            return "NOT_SCRAPED_REFERENCE"
        if not card.scrape.looks_like_product_page:
            return "REVIEW_ONLY_NOT_PRODUCT_PAGE_OR_THIN"
        if card.llm_reject_reason:
            return "LLM_UNAVAILABLE_OR_REJECTED_REVIEW_ONLY"
        if card.verification and card.verification.exact_product_check != "EXACT_MATCH":
            return "REVIEW_ONLY_WEAK_EXACTNESS"
        return "SUPPORTING_CANDIDATE"

    def _candidate_reason(self, state: ProductSearchState, card: CandidateScorecard, role: str) -> str:
        final = state.final_result
        tournament = getattr(state, "tournament_result", None)
        if role.startswith("TOURNAMENT_CHAMPION"):
            if final and final.needs_review:
                return f"Champion selected as product_url, but review-only because production gate status is {final.url_decision_status}."
            return "Champion selected as production-ready product_url."
        if role == "RUNNER_UP_SUPPORTING_EVIDENCE":
            return "Runner-up retained only as supporting evidence; product_url remains the tournament champion."
        if card.primary_reject_reason:
            return card.primary_reject_reason
        if card.hard_failures:
            return "; ".join(card.hard_failures)
        if card.verification and card.verification.blocking_reasons:
            return "; ".join(card.verification.blocking_reasons)
        if card.llm_reject_reason:
            return card.llm_reject_reason
        if card.scrape and not card.scrape.looks_like_product_page:
            return "Scraped page was thin, redirected, blocked, or not product-page-like."
        if card.verification and card.verification.exact_product_check != "EXACT_MATCH":
            return f"Not exact product evidence: {card.verification.exact_product_check}."
        if tournament:
            return "Candidate lost tournament comparison to champion."
        return "Supporting candidate."
