from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from product_url_v2.contracts import (
    BudgetPolicy,
    CandidateAssessment,
    DeliveryDecision,
    DeliveryStatus,
    GateStatus,
    IdentityMatch,
    ProductInput,
    SourceRole,
)


_GATE_RANK = {
    GateStatus.FAIL: 0,
    GateStatus.NOT_ASSESSED: 1,
    GateStatus.PASS: 2,
}
_IDENTITY_RANK = {
    IdentityMatch.MISMATCH: 0,
    IdentityMatch.UNVERIFIED: 1,
    IdentityMatch.PROBABLE: 2,
    IdentityMatch.EXACT: 3,
}
_MANUFACTURER_ROLES = {
    SourceRole.LOCAL_MANUFACTURER,
    SourceRole.GLOBAL_MANUFACTURER,
}
_LOCAL_COMMERCIAL_ROLES = {
    SourceRole.REQUESTED_RETAILER,
    SourceRole.COUNTRY_RETAILER,
}


@dataclass(frozen=True, slots=True)
class SearchObjective:
    sequence: int
    purpose: str
    scope: str
    required_signals: tuple[str, ...]
    rationale: str


def build_search_objectives(product: ProductInput) -> tuple[SearchObjective, ...]:
    """Return the three mandatory information-gain objectives.

    Search engines and queries are chosen adaptively at runtime, but the purpose
    of each paid action is stable and auditable.
    """

    first_signals = ["DIRECT_PRODUCT_URL", "MODEL_OR_PRODUCT_NAME"]
    first_purpose = "establish_exact_product_identity"
    first_rationale = (
        "Acquire authoritative identity evidence before optimizing retailer or feature coverage."
    )
    if product.ean:
        first_signals.insert(0, "EAN_OR_GTIN_EXACT_MATCH")
        first_purpose = "resolve_exact_identifier"
        first_rationale = "Use the supplied EAN/GTIN as the strongest exact identity anchor."

    second_signals = [
        "VARIANT",
        "PACK_CONFIGURATION",
        "QUANTITY_OR_SIZE",
        "COUNTRY_LANGUAGE_FORM",
        "DIRECT_PRODUCT_URL",
    ]
    if product.retailer_name:
        second_signals.append("REQUESTED_RETAILER_URL")

    return (
        SearchObjective(
            sequence=1,
            purpose=first_purpose,
            scope="country",
            required_signals=tuple(first_signals),
            rationale=first_rationale,
        ),
        SearchObjective(
            sequence=2,
            purpose="resolve_highest_identity_uncertainty",
            scope="country",
            required_signals=tuple(second_signals),
            rationale=(
                "Spend the second credit on the distinction most likely to cause a wrong-product, "
                "wrong-variant, or wrong-pack decision."
            ),
        ),
        SearchObjective(
            sequence=3,
            purpose="mandatory_direct_url_recovery",
            scope="global",
            required_signals=(
                "REAL_EXTERNAL_URL",
                "DIRECT_PRODUCT_PAGE",
                "MANUFACTURER_OR_RETAILER",
                "DURABLE_URL",
            ),
            rationale=(
                "The final credit must maximize recall of a real direct product page while retaining "
                "all known identity anchors and negative constraints."
            ),
        ),
    )


class CandidateAllocationPolicy:
    """Allocate scarce browser slots by evidence diversity, not raw score alone."""

    def __init__(self, budget: BudgetPolicy | None = None) -> None:
        self.budget = budget or BudgetPolicy()

    def select_for_browser(
        self,
        candidates: Sequence[CandidateAssessment],
    ) -> tuple[CandidateAssessment, ...]:
        limit = self.budget.max_browser_investigations
        eligible = [
            item
            for item in candidates
            if not item.browser_assessed
            and item.direct_product_page is not GateStatus.FAIL
            and item.durable_url is not GateStatus.FAIL
            and not item.has_identity_conflict
        ]
        ranked = sorted(eligible, key=self._pre_browser_rank, reverse=True)
        selected: list[CandidateAssessment] = []

        def add_best(predicate) -> None:
            for candidate in ranked:
                if len(selected) >= limit:
                    return
                if candidate in selected or not predicate(candidate):
                    continue
                selected.append(candidate)
                return

        # Cover source-authority and commercial-reference axes first.
        add_best(lambda item: item.source_role in _MANUFACTURER_ROLES)
        add_best(lambda item: item.source_role in _LOCAL_COMMERCIAL_ROLES)

        # Preserve one slot for a competing identity hypothesis or a new domain.
        selected_hypotheses = {item.hypothesis_id for item in selected if item.hypothesis_id}
        selected_domains = {item.domain for item in selected}
        add_best(
            lambda item: bool(
                (item.hypothesis_id and item.hypothesis_id not in selected_hypotheses)
                or item.domain not in selected_domains
            )
        )

        for candidate in ranked:
            if len(selected) >= limit:
                break
            if candidate not in selected:
                selected.append(candidate)
        return tuple(selected)

    @staticmethod
    def _pre_browser_rank(candidate: CandidateAssessment) -> tuple[float, ...]:
        return (
            float(_IDENTITY_RANK[candidate.identity_match]),
            candidate.identity_confidence,
            float(_GATE_RANK[candidate.direct_product_page]),
            float(candidate.source_authority),
            float(_GATE_RANK[candidate.country_match]),
            float(_GATE_RANK[candidate.retailer_match]),
            candidate.search_support,
            float(-(candidate.search_rank or 9999)),
        )


class MandatoryURLDeliveryPolicy:
    """Select the strongest real URL without conflating coding readiness.

    Invariant:
      * VERIFIED and REVIEW_REQUIRED always contain a URL.
      * FAILED is legal only when no review-eligible direct candidate exists.
    """

    def select(
        self,
        candidates: Iterable[CandidateAssessment],
    ) -> DeliveryDecision:
        values = tuple(candidates)
        strict = tuple(item for item in values if item.strictly_verified)
        if strict:
            selected = max(strict, key=self._strict_rank)
            return DeliveryDecision(
                status=DeliveryStatus.VERIFIED,
                selected_candidate_id=selected.candidate_id,
                selected_url=selected.url,
                strictly_verified=True,
                coding_ready=True,
                reasons=(
                    "Exact product identity verified.",
                    "Direct page, browser access, extraction and durability gates passed.",
                    "Required coding evidence is complete on the selected page.",
                ),
                considered_candidate_ids=tuple(item.candidate_id for item in values),
            )

        review = tuple(item for item in values if item.review_eligible)
        if review:
            selected = max(review, key=self._review_rank)
            return DeliveryDecision(
                status=DeliveryStatus.REVIEW_REQUIRED,
                selected_candidate_id=selected.candidate_id,
                selected_url=selected.url,
                strictly_verified=False,
                coding_ready=False,
                reasons=self._review_reasons(selected),
                considered_candidate_ids=tuple(item.candidate_id for item in values),
            )

        return DeliveryDecision(
            status=DeliveryStatus.FAILED,
            selected_candidate_id=None,
            selected_url=None,
            strictly_verified=False,
            coding_ready=False,
            reasons=(
                "No real direct candidate survived explicit wrong-page, wrong-product, conflict, or transient-URL blockers.",
                "The mandatory search and recovery budget must be exhausted before this result is emitted.",
            ),
            considered_candidate_ids=tuple(item.candidate_id for item in values),
        )

    @staticmethod
    def _strict_rank(candidate: CandidateAssessment) -> tuple[float, ...]:
        return (
            float(candidate.source_authority),
            float(_GATE_RANK[candidate.country_match]),
            float(_GATE_RANK[candidate.retailer_match]),
            candidate.identity_confidence,
            candidate.search_support,
            float(-(candidate.search_rank or 9999)),
        )

    @staticmethod
    def _review_rank(candidate: CandidateAssessment) -> tuple[float, ...]:
        return (
            float(_IDENTITY_RANK[candidate.identity_match]),
            candidate.identity_confidence,
            float(_GATE_RANK[candidate.direct_product_page]),
            float(_GATE_RANK[candidate.durable_url]),
            float(_GATE_RANK[candidate.browser_access]),
            float(_GATE_RANK[candidate.text_extractable]),
            float(candidate.source_authority),
            float(_GATE_RANK[candidate.country_match]),
            float(_GATE_RANK[candidate.retailer_match]),
            float(_GATE_RANK[candidate.coding_evidence_complete]),
            candidate.search_support,
            float(-(candidate.search_rank or 9999)),
        )

    @staticmethod
    def _review_reasons(candidate: CandidateAssessment) -> tuple[str, ...]:
        reasons = [
            "The strongest real direct product-page candidate is retained for human review.",
        ]
        if candidate.identity_match is IdentityMatch.EXACT:
            reasons.append("Identity evidence supports the exact product.")
        elif candidate.identity_match is IdentityMatch.PROBABLE:
            reasons.append("Identity is probable but retains unresolved uncertainty.")
        else:
            reasons.append("Identity was not fully verified and must be confirmed by the reviewer.")
        if candidate.browser_access is GateStatus.FAIL:
            reasons.append(
                "The automation browser could not access the page; this is not represented as proof that a human cannot open it."
            )
        elif candidate.browser_access is GateStatus.NOT_ASSESSED:
            reasons.append("Rendered-browser accessibility was not assessed.")
        if candidate.text_extractable is GateStatus.FAIL:
            reasons.append("Automated text extraction failed; the URL remains usable for manual coding review.")
        elif candidate.text_extractable is GateStatus.NOT_ASSESSED:
            reasons.append("Automated text extraction was not assessed.")
        if candidate.coding_evidence_complete is GateStatus.FAIL:
            reasons.append("The page does not contain every requested coding fact.")
        elif candidate.coding_evidence_complete is GateStatus.NOT_ASSESSED:
            reasons.append("Requested coding-feature completeness was not assessed.")
        reasons.extend(candidate.warnings[:3])
        return tuple(dict.fromkeys(reasons))
