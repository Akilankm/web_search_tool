from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


NO_URL_OUTCOME_CODE = "NO_SAFE_DIRECT_PRODUCT_URL_FOUND"
NO_URL_DELIVERY_STATUS = "NO_SAFE_DIRECT_PRODUCT_URL_FOUND_AFTER_BOUNDED_SEARCH"
_NO_URL_EXCEPTION_PREFIX = "MANDATORY_PRODUCT_URL_NOT_FOUND:"
_PATCHED = False


def is_structured_no_url_outcome(result: Mapping[str, Any]) -> bool:
    """Return True only for the explicit, auditable no-safe-URL business outcome."""

    outcome = result.get("resolution_outcome")
    delivery = result.get("url_delivery")
    return bool(
        isinstance(outcome, Mapping)
        and outcome.get("code") == NO_URL_OUTCOME_CODE
        and result.get("job_status") == "REVIEW_REQUIRED"
        and isinstance(delivery, Mapping)
        and delivery.get("status") == NO_URL_DELIVERY_STATUS
        and delivery.get("delivered") is False
        and not result.get("primary_url")
    )


def _stage_summary(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    search = result.get("search") if isinstance(result.get("search"), Mapping) else {}
    stages = search.get("stages") if isinstance(search, Mapping) else []
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(stages or [], start=1):
        if not isinstance(raw, Mapping):
            continue
        output.append(
            {
                "sequence": index,
                "name": raw.get("name") or raw.get("market_stage") or raw.get("stage"),
                "engine": raw.get("engine"),
                "query": raw.get("query"),
                "scope": raw.get("scope"),
                "results_returned": raw.get("results_returned") or raw.get("result_count") or 0,
                "new_candidate_urls": raw.get("new_candidate_urls") or raw.get("candidate_count") or 0,
                "qualified_candidates": raw.get("candidates_qualified") or raw.get("qualified_candidates") or 0,
                "working_url_found": bool(raw.get("working_url_found")),
                "status": raw.get("status"),
                "reason": raw.get("reason"),
            }
        )
    return output


def _write_no_url_artifacts(result: dict[str, Any]) -> None:
    root_value = result.get("artifact_dir")
    if not root_value:
        return
    root = Path(str(root_value))
    root.mkdir(parents=True, exist_ok=True)
    files = {
        "no_url_resolution.json": result.get("resolution_outcome") or {},
        "mandatory_url_delivery.json": result.get("url_delivery") or {},
        "primary_url_acceptance.json": result.get("primary_url_acceptance") or {},
        "source_selection.json": result.get("source_selection") or {},
        "orchestrated_result.json": result,
    }
    for name, payload in files.items():
        target = root / name
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)


def build_structured_no_url_outcome(
    result: dict[str, Any],
    *,
    reason: str | None = None,
) -> dict[str, Any]:
    """Convert search exhaustion into an explicit review result, never a false success."""

    search = dict(result.get("search") or {})
    stages = _stage_summary(result)
    credits_used = search.get("serpapi_requests_used")
    if credits_used is None:
        credits_used = len(stages)

    investigations = list(result.get("candidate_investigations") or [])
    assessments = list(result.get("feature_assessments") or [])
    browser_evidence = list(result.get("browser_evidence") or [])
    reason_text = (
        reason
        or "The bounded manufacturer, local-market and global search route did not produce "
        "a safe direct external product-page URL."
    )

    outcome = {
        "code": NO_URL_OUTCOME_CODE,
        "category": "CONTROLLED_BUSINESS_NO_MATCH",
        "terminal_status": "REVIEW_REQUIRED",
        "message": reason_text,
        "safe_to_retry": True,
        "requires_human_review": True,
        "url_fabricated": False,
        "search_budget_exhausted": True,
        "serpapi_requests_used": credits_used,
        "serpapi_request_limit": search.get("serpapi_request_limit", 3),
        "search_stages": stages,
        "candidate_investigations": len(investigations),
        "feature_assessments": len(assessments),
        "browser_evidence_records": len(browser_evidence),
        "suggested_next_actions": [
            "Verify or add the EAN/GTIN when available.",
            "Verify the product main text, model, variant and pack description.",
            "Provide the expected retailer or a known candidate URL when available.",
            "Review the three search-stage queries and rejected candidates before expanding the search budget.",
        ],
    }

    acceptance = dict(result.get("primary_url_acceptance") or {})
    reasons = list(acceptance.get("reasons") or [])
    if NO_URL_OUTCOME_CODE not in reasons:
        reasons.append(NO_URL_OUTCOME_CODE)
    acceptance.update(
        {
            "accepted": False,
            "primary_url": None,
            "delivery_required": True,
            "delivery_status": NO_URL_DELIVERY_STATUS,
            "source_role": "NONE",
            "source_tier": None,
            "source_tier_name": "NONE",
            "manufacturer_url": None,
            "retailer_url": None,
            "selection_reason": NO_URL_DELIVERY_STATUS,
            "reasons": reasons,
        }
    )

    product_match = dict(result.get("product_match") or {})
    product_match.update(
        {
            "product_url": None,
            "best_available_url": None,
            "best_reference_url": None,
            "verified_exact_url": None,
            "resolution_status": "REVIEW_REQUIRED_NO_SAFE_DIRECT_URL",
            "url_decision_status": NO_URL_DELIVERY_STATUS,
            "validation_status": "NEEDS_REVIEW",
            "match_reason": NO_URL_OUTCOME_CODE,
            "needs_review": True,
            "selected_with_warning": False,
            "primary_reject_reason": NO_URL_OUTCOME_CODE,
            "primary_url_role": "NONE",
            "manufacturer_url": None,
            "retailer_url": None,
            "source_selection_reason": NO_URL_DELIVERY_STATUS,
        }
    )

    evidence_set = dict(result.get("evidence_set") or {})
    evidence_set.update(
        {
            "primary_url": None,
            "selected_urls": [],
            "supplementary_urls": [],
            "status": "REVIEW_REQUIRED_NO_SAFE_DIRECT_PRODUCT_URL",
            "coding_ready": False,
            "primary_url_role": "NONE",
            "manufacturer_url": None,
            "retailer_url": None,
        }
    )

    source_selection = {
        "policy": "MANUFACTURER_FIRST_AFTER_PRODUCTION_GATES",
        "primary_url": None,
        "primary_url_role": "NONE",
        "source_role": "NONE",
        "source_tier": None,
        "source_tier_name": "NONE",
        "manufacturer_url": None,
        "retailer_url": None,
        "selection_reason": NO_URL_DELIVERY_STATUS,
        "manufacturer_priority_is_conditional": True,
        "required_gates": [
            "exact_product_identity",
            "browser_openable",
            "text_scrapable",
            "rendered_product_verified",
            "requested_feature_coverage",
            "durable_non_expiring_url",
        ],
        "fallback_rule": (
            "Return an explicit review outcome when no safe direct product page exists; "
            "never fabricate or promote an indirect search/category URL."
        ),
    }

    search.update(
        {
            "no_safe_direct_url_found": True,
            "search_exhaustion_outcome": NO_URL_OUTCOME_CODE,
            "serpapi_requests_used": credits_used,
        }
    )

    result.update(
        {
            "job_status": "REVIEW_REQUIRED",
            "coding_ready": False,
            "primary_url": None,
            "primary_url_role": "NONE",
            "manufacturer_url": None,
            "retailer_url": None,
            "supplementary_urls": [],
            "primary_url_acceptance": acceptance,
            "product_match": product_match,
            "evidence_set": evidence_set,
            "source_selection": source_selection,
            "search": search,
            "url_delivery": {
                "required": True,
                "delivered": False,
                "url": None,
                "strictly_verified": False,
                "status": NO_URL_DELIVERY_STATUS,
                "empty_url_is_success": False,
                "primary_url_role": "NONE",
                "manufacturer_url": None,
                "retailer_url": None,
                "manufacturer_first_policy": True,
            },
            "resolution_outcome": outcome,
        }
    )
    _write_no_url_artifacts(result)
    return result


def apply_structured_no_url_outcome_patch() -> None:
    """Install a narrow recovery for search exhaustion while preserving real failures."""

    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    from src.product_evidence_harness import mandatory_url_policy

    original_enforce = mandatory_url_policy._enforce_orchestrated_delivery

    def enforce(result: dict[str, Any]) -> dict[str, Any]:
        try:
            return original_enforce(result)
        except RuntimeError as exc:
            message = str(exc)
            if not message.startswith(_NO_URL_EXCEPTION_PREFIX):
                raise
            return build_structured_no_url_outcome(result, reason=message)

    mandatory_url_policy._enforce_orchestrated_delivery = enforce

    from src.product_evidence_harness.agent_service.strict_orchestrator import (
        StrictProductEvidenceOrchestrator,
    )

    current_run = StrictProductEvidenceOrchestrator.run

    def run(self, payload, *, progress=None):
        result = current_run(self, payload, progress=progress)
        if is_structured_no_url_outcome(result):
            return build_structured_no_url_outcome(
                result,
                reason=(result.get("resolution_outcome") or {}).get("message"),
            )
        return result

    StrictProductEvidenceOrchestrator.run = run
