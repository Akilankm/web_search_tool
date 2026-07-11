from __future__ import annotations

from dataclasses import replace

from src.product_evidence_harness.contracts import ProductSearchState, ProductURLMatch
from src.product_evidence_harness.pipeline import ProductEvidenceHarness as BaseProductEvidenceHarness
from src.product_evidence_harness.production_url import ProductionURLGate


class ProductEvidenceHarness(BaseProductEvidenceHarness):
    """Compatibility surface for existing notebooks and tests.

    New development must use ``FeatureAwareProductEvidenceHarness``. This class
    retains the pre-tournament behavior where the best discovered URL remains in
    ``product_url`` with an explicit review status when it is not production-ready.
    """

    @staticmethod
    def _enforce_nonempty_product_url(match: ProductURLMatch, state: ProductSearchState) -> ProductURLMatch:
        url = match.product_url or match.best_available_url or match.best_reference_url
        if not url and state.candidates:
            url = state.candidates[0].url
        if not url:
            return match

        scrape = state.scrapes.get(url)
        if scrape is None:
            status = "DISCOVERED_CANDIDATE_URL_UNSCRAPED_NEEDS_REVIEW"
            scrapable = False
        elif scrape.is_scrapable:
            status = match.url_decision_status or "BEST_AVAILABLE_PRODUCT_URL_NEEDS_REVIEW"
            scrapable = True
        else:
            status = "BEST_AVAILABLE_PRODUCT_URL_NOT_SCRAPABLE_NEEDS_REVIEW"
            scrapable = False

        return replace(
            match,
            product_url=url,
            best_available_url=url,
            best_reference_url=url,
            needs_review=True,
            is_scrapable=scrapable,
            url_decision_status=status,
            resolution_status=status,
            selected_with_warning=True,
        )

    @staticmethod
    def _enforce_production_grade_product_url(
        match: ProductURLMatch,
        state: ProductSearchState,
        *,
        production_gate: ProductionURLGate | None = None,
    ) -> ProductURLMatch:
        strict = BaseProductEvidenceHarness._enforce_production_grade_product_url(
            match,
            state,
            production_gate=production_gate,
        )
        if strict.product_url:
            return strict

        fallback_seed = replace(
            match,
            best_available_url=strict.best_available_url or match.best_available_url,
            best_reference_url=strict.best_reference_url or match.best_reference_url,
            url_decision_status=strict.url_decision_status or match.url_decision_status,
        )
        fallback = ProductEvidenceHarness._enforce_nonempty_product_url(fallback_seed, state)
        if not fallback.product_url:
            return strict
        return replace(
            fallback,
            verified_exact_url=None,
            needs_review=True,
            is_exact_product_match=False,
            primary_reject_reason="PRODUCT_URL_NOT_PRODUCTION_GRADE",
            match_reason="best available URL retained for compatibility review",
        )


HarnessProductURLFinderPipeline = ProductEvidenceHarness
HybridProductURLFinderPipeline = ProductEvidenceHarness
