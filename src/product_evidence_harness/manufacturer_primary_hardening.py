from __future__ import annotations

from dataclasses import replace

from src.product_evidence_harness.pipeline import ProductEvidenceHarness
from src.product_evidence_harness.production_url import ProductionURLGate
from src.product_evidence_harness.source_authority import source_role, source_tier


_PATCHED = False


def _card_for_url(state, url: str | None):
    if not url:
        return None
    return next(
        (card for card in state.scorecards if card.candidate.url == url),
        None,
    )


def apply_manufacturer_primary_hardening() -> None:
    """Keep manufacturer authority intact through legacy production promotion."""

    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    def best_production_card(self, state):
        assessed = [(card, self.assess_card(card)) for card in state.scorecards]
        ready = [
            (card, assessment)
            for card, assessment in assessed
            if assessment.production_ready
        ]
        if not ready:
            return None, None
        return sorted(
            ready,
            key=lambda pair: (
                100 - source_tier(pair[0].candidate),
                1 if pair[0].country_check == "MATCHED" else 0,
                1 if pair[0].retailer_check == "MATCHED" else 0,
                pair[1].score,
                pair[0].richness_score,
                pair[0].final_confidence,
            ),
            reverse=True,
        )[0]

    ProductionURLGate.best_production_card = best_production_card

    current_enforce = ProductEvidenceHarness._enforce_production_grade_product_url

    def enforce(match, state, *, production_gate=None):
        promoted = current_enforce(
            match,
            state,
            production_gate=production_gate,
        )
        stage_reason = str(
            getattr(match, "termination_reason", "")
            or getattr(state, "termination_reason", "")
        ).upper()
        if "MANUFACTURER_PRIMARY" not in stage_reason:
            return promoted

        selected_url = promoted.product_url or promoted.best_available_url
        card = _card_for_url(state, selected_url)
        if card is None or source_role(card.candidate) == "MANUFACTURER":
            return promoted

        # Preserve the retailer as a review/commercial reference but do not let
        # it satisfy early-stop during the manufacturer-targeted first credit.
        retained = promoted.product_url or promoted.best_available_url
        return replace(
            promoted,
            product_url=None,
            best_available_url=retained,
            best_reference_url=retained,
            verified_exact_url=None,
            validation_status="NEEDS_REVIEW",
            resolution_status="SEARCH_CONTINUES",
            url_decision_status="CONTINUE_AFTER_MANUFACTURER_STAGE",
            match_reason="MANUFACTURER_STAGE_RETAILER_DEFERRED",
            needs_review=True,
            selected_with_warning=True,
        )

    ProductEvidenceHarness._enforce_production_grade_product_url = staticmethod(enforce)
