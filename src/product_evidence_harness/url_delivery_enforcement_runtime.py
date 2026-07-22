from __future__ import annotations

import sys
from typing import Any

from src.product_evidence_harness.url_delivery_recovery import (
    collect_delivery_candidates,
    select_best_delivery_candidate,
)


_PATCHED = False


def apply_url_delivery_enforcement_patch() -> None:
    """Inject the strongest review URL before terminal no-URL handling."""

    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    from src.product_evidence_harness import mandatory_url_policy

    current = mandatory_url_policy._enforce_orchestrated_delivery
    if getattr(current, "_url_delivery_enforcement_wrapper", False):
        return

    def enforce(result: dict[str, Any]) -> dict[str, Any]:
        if not result.get("primary_url"):
            candidate = select_best_delivery_candidate(result)
            if candidate is not None:
                candidates = collect_delivery_candidates(result)
                result["url_delivery_recovery"] = {
                    "schema_version": "url-delivery-recovery-v1",
                    "selected": candidate.to_dict(),
                    "candidate_count": len(candidates),
                    "policy": (
                        "Deliver the strongest real direct product URL that is not a confirmed "
                        "product or variant mismatch."
                    ),
                }
                result["primary_url"] = candidate.url

                product_match = dict(result.get("product_match") or {})
                product_match["product_url"] = candidate.url
                product_match["best_available_url"] = candidate.url
                product_match.setdefault("best_reference_url", candidate.url)
                result["product_match"] = product_match

                evidence_set = dict(result.get("evidence_set") or {})
                existing = [
                    str(item)
                    for item in evidence_set.get("selected_urls") or []
                    if item
                ]
                evidence_set["primary_url"] = candidate.url
                evidence_set["selected_urls"] = list(
                    dict.fromkeys([candidate.url, *existing])
                )
                result["evidence_set"] = evidence_set

                selection = dict(result.get("source_selection") or {})
                if candidate.source_role not in {"", "NONE", "UNCLASSIFIED"}:
                    selection.setdefault("source_role", candidate.source_role)
                    result.setdefault("primary_url_role", candidate.source_role)
                if candidate.source_tier not in {"", "NONE", "UNCLASSIFIED"}:
                    selection.setdefault("source_tier_name", candidate.source_tier)
                result["source_selection"] = selection

        return current(result)

    enforce._url_delivery_enforcement_wrapper = True
    mandatory_url_policy._enforce_orchestrated_delivery = enforce

    # The repository can be imported as either src.product_evidence_harness or
    # product_evidence_harness. Point both names and package attributes to the
    # same patched module so the delivery policy cannot diverge by import path.
    sys.modules["product_evidence_harness.mandatory_url_policy"] = mandatory_url_policy
    package = sys.modules.get("product_evidence_harness")
    if package is not None:
        setattr(package, "mandatory_url_policy", mandatory_url_policy)
