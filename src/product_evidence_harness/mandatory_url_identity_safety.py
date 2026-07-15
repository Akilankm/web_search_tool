from __future__ import annotations

from typing import Any, Sequence

from src.product_evidence_harness.contracts import CandidateScorecard


def _known_wrong_card(card: CandidateScorecard) -> bool:
    verification = card.verification
    if verification is not None:
        if str(verification.identity_status or "").upper() in {
            "MISMATCH",
            "REJECTED",
            "CONFLICT",
        }:
            return True
        if str(verification.variant_check or "").upper() == "CONFLICT":
            return True
        if str(verification.exact_product_check or "").upper() in {
            "MISMATCH",
            "NOT_EXACT",
            "WRONG_PRODUCT",
        }:
            return True
        if bool(getattr(verification, "ean_conflict_is_blocking", False)):
            return True

    normalized = " ".join(str(item or "") for item in card.hard_failures).lower()
    definitive_markers = (
        "variant conflict",
        "wrong variant",
        "wrong product",
        "identity mismatch",
        "ean conflict",
        "gtin conflict",
        "exact product mismatch",
    )
    return any(marker in normalized for marker in definitive_markers)


def _known_wrong_product_match(match: dict[str, Any]) -> bool:
    if str(match.get("variant_check") or "").upper() == "CONFLICT":
        return True
    if str(match.get("identity_status") or "").upper() in {
        "MISMATCH",
        "REJECTED",
        "CONFLICT",
    }:
        return True
    if str(match.get("exact_product_check") or "").upper() in {
        "MISMATCH",
        "NOT_EXACT",
        "WRONG_PRODUCT",
    }:
        return True
    if bool(match.get("ean_conflict_is_blocking")):
        return True
    blockers = " ".join(
        str(value or "")
        for value in (
            match.get("blocking_reasons"),
            match.get("primary_reject_reason"),
            *(match.get("hard_failures") or ()),
        )
    ).lower()
    return any(
        marker in blockers
        for marker in (
            "variant conflict",
            "wrong variant",
            "wrong product",
            "identity mismatch",
            "ean conflict",
            "gtin conflict",
            "exact product mismatch",
        )
    )


def apply_mandatory_url_identity_safety() -> None:
    import src.product_evidence_harness.mandatory_url_policy as policy

    if getattr(policy, "_identity_safety_applied", False):
        return

    original_card_rank = policy._card_rank

    def strongest(scorecards: Sequence[CandidateScorecard]):
        ranked = sorted(
            (
                card
                for card in scorecards
                if policy._direct_external_url(card.candidate.url)
                and not _known_wrong_card(card)
            ),
            key=original_card_rank,
            reverse=True,
        )
        return ranked[0] if ranked else None

    def first_url(result: dict[str, Any]):
        match = result.get("product_match") or {}
        blocked: set[str] = set()
        if _known_wrong_product_match(match):
            for key in (
                "product_url",
                "best_available_url",
                "best_reference_url",
                "scrape_final_url",
            ):
                value = policy._direct_external_url(match.get(key))
                if value:
                    blocked.add(value)

        seen: set[str] = set()
        for value in policy._candidate_urls_from_result(result):
            url = policy._direct_external_url(value)
            if not url or url in seen or url in blocked:
                continue
            seen.add(url)
            return url
        return None

    policy._strongest_deliverable_card = strongest
    policy._first_deliverable_url = first_url
    policy._identity_safety_applied = True
