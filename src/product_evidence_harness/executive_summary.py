from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


EXECUTIVE_SUMMARY_SCHEMA_VERSION = "url-decision-summary-v1"


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number == number and number not in {float("inf"), float("-inf")} else None


def _integer(value: Any, default: int = 0) -> int:
    number = _number(value)
    return int(number) if number is not None else default


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}, ()):
            return value
    return None


def _gate_state(value: Any) -> str:
    if value is True:
        return "PASS"
    if value is False:
        return "FAIL"
    return "NOT_ASSESSED"


def _coverage(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return max(0.0, min(1.0, number / 100.0 if number > 1.0 else number))


def _count_unresolved(identity: Mapping[str, Any]) -> int:
    return len(identity.get("uncertainties") or []) + len(identity.get("unknowns") or [])


def _count_contradictions(identity: Mapping[str, Any]) -> int:
    count = 0
    for item in _records(identity.get("hypotheses")):
        count += len(item.get("contradicting_evidence_ids") or [])
    for item in _records(identity.get("evidence_ledger")):
        if _text(item.get("polarity")).upper() in {"CONTRADICTS", "CONFLICTS", "NEGATIVE"}:
            count += 1
    return count


def _search_metrics(result: Mapping[str, Any]) -> dict[str, int]:
    search = _mapping(result.get("search"))
    stages = _records(search.get("stages"))

    results_seen = sum(
        _integer(_first(item, "results_returned", "raw_results_seen", "result_count"))
        for item in stages
    )
    new_candidates = sum(
        _integer(_first(item, "new_candidate_urls", "candidate_count"))
        for item in stages
    )
    canonical_candidates = max(
        [_integer(item.get("canonical_candidates_seen")) for item in stages] or [0]
    )
    candidates_seen = max(new_candidates, canonical_candidates)
    qualified = sum(
        _integer(_first(item, "candidates_qualified", "qualified_candidates"))
        for item in stages
    )
    scraped = sum(_integer(item.get("candidates_scraped")) for item in stages)

    agentic = _mapping(result.get("agentic_browser"))
    investigations = _records(result.get("candidate_investigations"))
    browser_evidence = _records(result.get("browser_evidence"))
    browser_admitted = _integer(
        agentic.get("candidate_urls_admitted"),
        len(investigations) or len(browser_evidence),
    )
    browser_completed = _integer(
        agentic.get("candidate_investigations_completed"),
        sum(1 for item in investigations if _text(item.get("status")).upper() == "COMPLETED")
        or len(browser_evidence),
    )

    credits_used = _integer(
        _first(search, "serpapi_requests_used", "serpapi_credits_used"),
        len(stages),
    )
    credits_limit = _integer(search.get("serpapi_request_limit"), max(credits_used, 3))

    return {
        "search_stages": len(stages),
        "search_actions_used": credits_used,
        "search_action_limit": credits_limit,
        "results_seen": results_seen,
        "candidate_urls_seen": candidates_seen,
        "qualified_candidates": qualified,
        "pages_extracted": scraped,
        "browser_candidates_admitted": browser_admitted,
        "browser_investigations_completed": browser_completed,
    }


def _candidate_rows(result: Mapping[str, Any], selected_url: str | None) -> list[dict[str, Any]]:
    browser_by_url: dict[str, dict[str, Any]] = {}
    for item in _records(result.get("browser_evidence")):
        url = _text(item.get("final_url") or item.get("requested_url"))
        if url:
            browser_by_url[url] = item

    rows: list[dict[str, Any]] = []
    for assessment in _records(result.get("feature_assessments")):
        url = _text(assessment.get("url"))
        if not url:
            continue
        browser = browser_by_url.get(url, {})
        coverage = _coverage(
            _first(assessment, "coverage", "total_coverage", "required_coverage")
        )
        rejection_reasons = assessment.get("rejection_reasons") or assessment.get("reasons") or []
        if isinstance(rejection_reasons, str):
            rejection_reasons = [rejection_reasons]
        rows.append(
            {
                "selected": url == selected_url,
                "url": url,
                "source_role": _text(
                    _first(assessment, "source_role", "primary_url_role", "selection_scope"),
                    "UNCLASSIFIED",
                ),
                "identity_status": _text(assessment.get("identity_status"), "NOT_ASSESSED"),
                "coverage": coverage,
                "browser_openable": browser.get("browser_openable"),
                "text_scrapable": browser.get("text_scrapable"),
                "durable_url": _first(assessment, "durable_url", "is_durable"),
                "missing_features": list(assessment.get("missing_features") or []),
                "conflicting_features": list(assessment.get("conflicting_features") or []),
                "decision": "SELECTED" if url == selected_url else "NOT_SELECTED",
                "reason": "; ".join(_text(item) for item in rejection_reasons if _text(item))[:800],
            }
        )

    if selected_url and not any(row["url"] == selected_url for row in rows):
        acceptance = _mapping(result.get("primary_url_acceptance"))
        rows.insert(
            0,
            {
                "selected": True,
                "url": selected_url,
                "source_role": _text(
                    _first(
                        _mapping(result.get("source_selection")),
                        "source_role",
                        "primary_url_role",
                    ),
                    _text(result.get("primary_url_role"), "SELECTED_SOURCE"),
                ),
                "identity_status": "VERIFIED" if acceptance.get("exact_product_verified") is True else "NOT_ASSESSED",
                "coverage": _coverage(acceptance.get("feature_coverage")),
                "browser_openable": acceptance.get("browser_openable"),
                "text_scrapable": acceptance.get("text_scrapable"),
                "durable_url": acceptance.get("durable_url"),
                "missing_features": [],
                "conflicting_features": [],
                "decision": "SELECTED",
                "reason": _text(acceptance.get("selection_reason")),
            },
        )

    return sorted(
        rows,
        key=lambda row: (
            bool(row.get("selected")),
            _text(row.get("identity_status")).upper() in {"VERIFIED", "EXACT", "PROBABLE"},
            row.get("coverage") or 0.0,
        ),
        reverse=True,
    )[:12]


def _decision_reasons(
    result: Mapping[str, Any],
    *,
    selected_url: str | None,
    usability_checks: list[dict[str, Any]],
) -> list[str]:
    acceptance = _mapping(result.get("primary_url_acceptance"))
    selection = _mapping(result.get("source_selection"))
    outcome = _mapping(result.get("resolution_outcome"))
    reasons: list[str] = []

    for value in (
        selection.get("selection_reason"),
        acceptance.get("selection_reason"),
        outcome.get("message"),
    ):
        text = _text(value)
        if text and text not in reasons:
            reasons.append(text)

    raw_reasons = acceptance.get("reasons") or []
    if isinstance(raw_reasons, str):
        raw_reasons = [raw_reasons]
    for value in raw_reasons:
        text = _text(value).replace("_", " ").strip()
        if text and text not in reasons:
            reasons.append(text)

    if selected_url:
        passed = [item["label"] for item in usability_checks if item["status"] == "PASS"]
        if passed:
            reasons.append("Passed checks: " + ", ".join(passed) + ".")
    else:
        rejected: list[str] = []
        for assessment in _records(result.get("feature_assessments")):
            raw = assessment.get("rejection_reasons") or assessment.get("reasons") or []
            if isinstance(raw, str):
                raw = [raw]
            for value in raw:
                text = _text(value).replace("_", " ")
                if text and text not in rejected:
                    rejected.append(text)
        if rejected:
            reasons.append("Leading rejection reasons: " + "; ".join(rejected[:5]) + ".")
        reasons.append("No indirect, mismatched, blocked, incomplete or expiring URL was promoted as a valid result.")

    return reasons[:8]


def build_executive_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    """Build a decision-first, auditable summary for UI, API and review artifacts."""

    identity = _mapping(result.get("product_identification"))
    hypothesis = _mapping(
        identity.get("leading_hypothesis")
        or identity.get("selected_hypothesis")
        or identity.get("winning_hypothesis")
    )
    product_match = _mapping(result.get("product_match"))
    delivery = _mapping(result.get("url_delivery"))
    acceptance = _mapping(result.get("primary_url_acceptance"))
    selection = _mapping(result.get("source_selection"))
    evidence_set = _mapping(result.get("evidence_set"))

    selected_url = _text(
        result.get("primary_url")
        or delivery.get("url")
        or product_match.get("product_url")
    ) or None
    identity_status = _text(
        identity.get("resolution_status") or product_match.get("identity_status"),
        "UNKNOWN",
    ).upper()
    product_name = _text(
        hypothesis.get("canonical_name")
        or identity.get("canonical_name")
        or identity.get("product_name")
        or (result.get("product") or {}).get("main_text"),
        "Product identity not resolved",
    )
    identity_confidence = _number(
        _first(hypothesis, "posterior_probability", "confidence", "score")
        or _first(identity, "confidence", "leading_probability")
        or product_match.get("confidence")
    )
    if identity_confidence is not None and identity_confidence > 1.0:
        identity_confidence /= 100.0
    if identity_confidence is not None:
        identity_confidence = max(0.0, min(1.0, identity_confidence))

    search_metrics = _search_metrics(result)
    claims = _records(identity.get("claims"))
    evidence = _records(identity.get("evidence_ledger"))
    hypotheses = _records(identity.get("hypotheses"))
    browser_evidence = _records(result.get("browser_evidence"))
    visual_assets = sum(len(item.get("visual_assets") or []) for item in browser_evidence)
    verified_claims = sum(
        1
        for item in claims
        if any(token in _text(item.get("status")).upper() for token in ("VERIFIED", "SUPPORTED", "CONFIRMED"))
    )

    strictly_verified = bool(delivery.get("strictly_verified")) or bool(acceptance.get("accepted"))
    delivered = bool(selected_url) and delivery.get("delivered") is not False
    coding_ready = bool(result.get("coding_ready"))
    source_role = _text(
        _first(selection, "source_role", "primary_url_role")
        or result.get("primary_url_role")
        or acceptance.get("source_role"),
        "NONE" if not selected_url else "UNCLASSIFIED",
    ).upper()
    source_tier = _text(
        _first(selection, "source_tier_name", "source_tier")
        or _first(acceptance, "source_tier_name", "source_tier"),
        "NONE" if not selected_url else "UNCLASSIFIED",
    ).upper()

    checks = [
        {
            "key": "browser_openable",
            "label": "Browser openable",
            "status": _gate_state(acceptance.get("browser_openable")),
            "value": acceptance.get("browser_openable"),
        },
        {
            "key": "text_scrapable",
            "label": "Text extractable",
            "status": _gate_state(acceptance.get("text_scrapable")),
            "value": acceptance.get("text_scrapable"),
        },
        {
            "key": "rendered_product_verified",
            "label": "Direct product page",
            "status": _gate_state(acceptance.get("rendered_product_verified")),
            "value": acceptance.get("rendered_product_verified"),
        },
        {
            "key": "exact_product_verified",
            "label": "Exact product identity",
            "status": _gate_state(acceptance.get("exact_product_verified")),
            "value": acceptance.get("exact_product_verified"),
        },
        {
            "key": "full_feature_coverage",
            "label": "Required evidence coverage",
            "status": _gate_state(acceptance.get("full_feature_coverage")),
            "value": acceptance.get("full_feature_coverage"),
        },
        {
            "key": "durable_url",
            "label": "Reusable non-expiring URL",
            "status": _gate_state(acceptance.get("durable_url")),
            "value": acceptance.get("durable_url"),
        },
    ]
    passed_checks = sum(1 for item in checks if item["status"] == "PASS")
    failed_checks = sum(1 for item in checks if item["status"] == "FAIL")
    assessed_checks = passed_checks + failed_checks

    if _text(result.get("job_status")).upper() == "FAILED":
        overall_status = "TECHNICAL_FAILURE"
        headline = "The URL decision could not be completed"
    elif selected_url and strictly_verified and coding_ready:
        overall_status = "JUSTIFIABLE_URL_FOUND"
        headline = "Justifiable product URL found"
    elif selected_url:
        overall_status = "URL_FOUND_REVIEW_REQUIRED"
        headline = "Candidate product URL found — review required"
    else:
        overall_status = "NO_JUSTIFIABLE_URL_FOUND"
        headline = "No justifiable product URL found"

    if selected_url:
        conclusion = (
            f"The system identified {product_name} with identity status {identity_status}"
            + (f" at {identity_confidence:.1%} confidence" if identity_confidence is not None else "")
            + f" and selected a {source_role.replace('_', ' ').lower()} URL. "
            + f"The URL passed {passed_checks} of {assessed_checks or len(checks)} assessed usability checks"
            + (" and is ready for downstream use." if coding_ready and strictly_verified else "; human review is still required before downstream use.")
        )
    else:
        conclusion = (
            f"The system evaluated the input as {product_name} with identity status {identity_status}"
            + (f" at {identity_confidence:.1%} confidence" if identity_confidence is not None else "")
            + f". It used {search_metrics['search_actions_used']} of {search_metrics['search_action_limit']} search actions, "
            + f"reviewed {search_metrics['results_seen']} results, qualified {search_metrics['qualified_candidates']} candidates, "
            + f"extracted {search_metrics['pages_extracted']} pages and completed {search_metrics['browser_investigations_completed']} browser investigations. "
            + "No candidate passed the required identity and usability gates, so the system returned an explicit no-URL decision instead of inventing or promoting an unsafe link."
        )

    source_status = (
        "SELECTED_AND_VERIFIED"
        if selected_url and strictly_verified
        else "SELECTED_FOR_REVIEW"
        if selected_url
        else "NO_JUSTIFIABLE_SOURCE"
    )
    evidence_count = len(evidence) + len(browser_evidence) + len(_records(result.get("feature_assessments")))
    evidence_status = "SUBSTANTIAL" if evidence_count >= 5 else "AVAILABLE" if evidence_count else "LIMITED"
    usability_status = (
        "READY"
        if selected_url and strictly_verified and coding_ready
        else "REVIEW_REQUIRED"
        if selected_url
        else "NOT_AVAILABLE"
    )

    reasons = _decision_reasons(result, selected_url=selected_url, usability_checks=checks)
    next_actions = list(_mapping(result.get("resolution_outcome")).get("suggested_next_actions") or [])
    if not next_actions and not selected_url:
        next_actions = [
            "Verify or add the EAN/GTIN when available.",
            "Confirm the model, variant, size and pack description.",
            "Provide the expected retailer or a known candidate URL when available.",
        ]

    summary = {
        "schema_version": EXECUTIVE_SUMMARY_SCHEMA_VERSION,
        "overall_status": overall_status,
        "headline": headline,
        "conclusion": conclusion,
        "selected_url": selected_url,
        "url_delivered": delivered,
        "strictly_verified": strictly_verified,
        "coding_ready": coding_ready,
        "product_name": product_name,
        "identity_status": identity_status,
        "identity_confidence": identity_confidence,
        "source_role": source_role,
        "source_tier": source_tier,
        "decision_reasons": reasons,
        "next_actions": [_text(item) for item in next_actions if _text(item)][:6],
        "work_completed": search_metrics,
        "pillars": {
            "source": {
                "status": source_status,
                "selected_url": selected_url,
                "source_role": source_role,
                "source_tier": source_tier,
                "manufacturer_url_available": bool(result.get("manufacturer_url")),
                "retailer_url_available": bool(result.get("retailer_url")),
                **search_metrics,
            },
            "evidence": {
                "status": evidence_status,
                "identity_claims": len(claims),
                "web_verified_claims": verified_claims,
                "atomic_evidence_items": len(evidence),
                "browser_evidence_records": len(browser_evidence),
                "visual_assets": visual_assets,
                "feature_assessments": len(_records(result.get("feature_assessments"))),
                "required_coverage": _coverage(evidence_set.get("required_coverage")),
                "critical_coverage": _coverage(evidence_set.get("critical_coverage")),
                "total_coverage": _coverage(evidence_set.get("total_coverage")),
            },
            "identity": {
                "status": identity_status,
                "identified_product": product_name,
                "confidence": identity_confidence,
                "hypotheses_considered": len(hypotheses),
                "unresolved_items": _count_unresolved(identity),
                "contradictions": _count_contradictions(identity),
            },
            "usability": {
                "status": usability_status,
                "url_delivered": delivered,
                "strictly_verified": strictly_verified,
                "coding_ready": coding_ready,
                "passed_checks": passed_checks,
                "failed_checks": failed_checks,
                "assessed_checks": assessed_checks,
                "checks": checks,
            },
        },
        "candidate_summary": _candidate_rows(result, selected_url),
    }
    return summary


def attach_executive_summary(result: dict[str, Any]) -> dict[str, Any]:
    summary = build_executive_summary(result)
    result["executive_summary"] = summary

    artifact_dir = _text(result.get("artifact_dir"))
    if artifact_dir:
        root = Path(artifact_dir)
        root.mkdir(parents=True, exist_ok=True)
        target = root / "executive_summary.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
    return result
