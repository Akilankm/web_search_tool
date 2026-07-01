from __future__ import annotations

from src.product_evidence_harness.contracts import CandidateScorecard, ProductSearchState


UNSAFE_VALIDATION_STATUSES = {"REJECTED", "FAILED", "BLOCKED"}
UNSAFE_IDENTITY_STATUSES = {"MISMATCH", "REJECTED", "FAILED", "BLOCKED"}
UNSAFE_EXACT_CHECKS = {"MISMATCH", "NOT_MATCHED", "CONFLICT", "FAILED", "REJECTED"}
UNSAFE_VARIANT_CHECKS = {"CONFLICT", "MISMATCH", "FAILED", "REJECTED"}


def _norm(value: object) -> str:
    return str(value or "").strip().upper()


def unsafe_review_reason(card: CandidateScorecard | None, *, min_confidence: float = 0.30) -> str:
    """Return an explicit reason when a candidate is unsafe as a review fallback.

    This gate is intentionally stricter than normal ranking. A fallback/review URL
    is still visible in candidate tables, but it must not be promoted to
    best_available_url / selected evidence when it is a hard product mismatch.
    """
    if card is None:
        return "NO_CANDIDATE_CARD"

    if card.final_confidence < min_confidence:
        return f"CONFIDENCE_BELOW_REVIEW_THRESHOLD:{card.final_confidence:.3f}<{min_confidence:.3f}"

    if _norm(card.validation_status) in UNSAFE_VALIDATION_STATUSES:
        return f"UNSAFE_VALIDATION_STATUS:{card.validation_status}"

    if card.primary_reject_reason:
        return f"PRIMARY_REJECT_REASON:{card.primary_reject_reason}"

    if card.hard_failures:
        return "HARD_FAILURES:" + "; ".join(card.hard_failures[:3])

    if card.llm_reject_reason:
        return f"LLM_REJECT_REASON:{card.llm_reject_reason}"

    if _norm(card.exact_product_check) in UNSAFE_EXACT_CHECKS:
        return f"UNSAFE_EXACT_PRODUCT_CHECK:{card.exact_product_check}"

    if _norm(card.variant_check) in UNSAFE_VARIANT_CHECKS:
        return f"UNSAFE_VARIANT_CHECK:{card.variant_check}"

    scrape = card.scrape
    if scrape is None:
        return "MISSING_SCRAPE_EVIDENCE"
    if not scrape.success:
        return "SCRAPE_NOT_SUCCESSFUL"
    if not scrape.is_scrapable:
        return "PAGE_NOT_SCRAPABLE"
    if not scrape.looks_like_product_page:
        return "NOT_A_PRODUCT_DETAIL_PAGE"

    verification = card.verification
    if verification is not None:
        if _norm(verification.identity_status) in UNSAFE_IDENTITY_STATUSES:
            return f"UNSAFE_IDENTITY_STATUS:{verification.identity_status}"
        if _norm(verification.exact_product_check) in UNSAFE_EXACT_CHECKS:
            return f"UNSAFE_VERIFICATION_EXACT_CHECK:{verification.exact_product_check}"
        if _norm(verification.variant_check) in UNSAFE_VARIANT_CHECKS:
            return f"UNSAFE_VERIFICATION_VARIANT_CHECK:{verification.variant_check}"
        if verification.blocking_reasons:
            return "VERIFICATION_BLOCKING_REASONS:" + "; ".join(verification.blocking_reasons[:3])
        if verification.variant_conflict_terms:
            return "VARIANT_CONFLICT_TERMS:" + "; ".join(verification.variant_conflict_terms[:3])

    return ""


def is_safe_review_candidate(card: CandidateScorecard | None, *, min_confidence: float = 0.30) -> bool:
    return unsafe_review_reason(card, min_confidence=min_confidence) == ""


def best_safe_review_card(state: ProductSearchState, *, min_confidence: float = 0.30) -> CandidateScorecard | None:
    cards = sorted(
        state.scorecards,
        key=lambda c: (c.final_confidence, c.weighted_confidence, c.richness_score),
        reverse=True,
    )
    for card in cards:
        if is_safe_review_candidate(card, min_confidence=min_confidence):
            return card
    return None


def card_for_url(state: ProductSearchState, url: str | None) -> CandidateScorecard | None:
    if not url:
        return None
    for card in state.scorecards:
        if card.candidate.url == url:
            return card
    return None
