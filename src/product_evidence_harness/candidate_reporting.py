from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from src.product_evidence_harness.candidate_precision import canonicalize_candidate_url
from src.product_evidence_harness.url_utils import domain_of


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_feature(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "feature").lower()).strip("_")


def _compact(values: Any) -> str:
    if values is None:
        return ""
    if isinstance(values, str):
        return values
    if isinstance(values, (list, tuple, set)):
        return "|".join(str(item) for item in values if str(item).strip())
    return str(values)


def _utility(scrape: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
    fetch_success = bool(scrape.get("success") and scrape.get("reachable"))
    content_extracted = bool(
        int(scrape.get("word_count") or 0) >= 20
        or int(scrape.get("markdown_chars") or 0) >= 400
    )
    probable_product = bool(
        scrape.get("looks_like_product_page")
        and not scrape.get("looks_like_homepage")
        and not scrape.get("is_soft_404")
    )
    identity_status = str(verification.get("identity_status") or "UNVERIFIED")
    identity_sufficient = identity_status in {"VERIFIED", "PROBABLE"}
    score = (
        0.15 * float(fetch_success)
        + 0.15 * float(content_extracted)
        + 0.25 * float(probable_product)
        + 0.30 * float(identity_sufficient)
        + 0.15 * min(1.0, _float(scrape.get("richness_score")))
    )
    accepted = bool(
        fetch_success
        and content_extracted
        and probable_product
        and identity_status != "MISMATCH"
        and score >= 0.48
    )
    return {
        "fetch_success": fetch_success,
        "content_extracted": content_extracted,
        "product_page_likelihood": round(
            0.45 * float(probable_product)
            + 0.25 * float(bool(scrape.get("page_product_name")))
            + 0.15 * float(bool(scrape.get("has_price")))
            + 0.15 * min(1.0, _float(scrape.get("richness_score"))),
            4,
        ),
        "content_utility_score": round(score, 4),
        "scrape_accepted": accepted,
    }


def _final_status(
    *,
    selected: bool,
    review_selected: bool,
    admission_reason: str,
    scrape_attempted: bool,
    fetch_success: bool,
    scrape_accepted: bool,
    identity_status: str,
    browser_admitted: bool,
    browser_openable: bool,
    coverage: float,
) -> str:
    if selected:
        return "STRICT_SELECTED"
    if review_selected:
        return "REVIEW_SELECTED"
    if "REJECTED_URL_TYPE" in admission_reason:
        return "SERP_REJECTED_URL_TYPE"
    if admission_reason.startswith("SERP_REJECTED"):
        return "SERP_REJECTED_LOW_IDENTITY"
    if not scrape_attempted:
        return "QUALIFIED_NOT_SCRAPED_BUDGET"
    if not fetch_success:
        return "SCRAPE_FAILED"
    if not scrape_accepted:
        return "SCRAPE_LOW_UTILITY"
    if identity_status == "MISMATCH":
        return "IDENTITY_REJECTED"
    if browser_admitted and not browser_openable:
        return "BROWSER_BLOCKED"
    if coverage < 1.0:
        return "FEATURE_INCOMPLETE"
    return "ELIGIBLE_NOT_SELECTED"


def build_candidate_records(
    result: dict[str, Any],
    candidate_state: dict[str, Any],
    browser_admissions: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    browser_admissions = browser_admissions or {}
    candidates = {
        canonicalize_candidate_url(item.get("url") or "") or str(item.get("url") or ""): item
        for item in candidate_state.get("candidates") or []
        if item.get("url")
    }
    admissions = {
        canonicalize_candidate_url(item.get("canonical_url") or item.get("original_url") or "")
        or str(item.get("canonical_url") or item.get("original_url") or ""): item
        for item in candidate_state.get("candidate_admissions") or []
    }
    scrapes = {
        canonicalize_candidate_url(url) or url: value
        for url, value in (candidate_state.get("scrapes") or {}).items()
    }
    verifications = {
        canonicalize_candidate_url(url) or url: value
        for url, value in (candidate_state.get("verifications") or {}).items()
    }
    scorecards: dict[str, dict[str, Any]] = {}
    for card in candidate_state.get("scorecards") or []:
        candidate = card.get("candidate") or {}
        url = canonicalize_candidate_url(candidate.get("url") or "") or candidate.get("url")
        if url:
            scorecards[url] = card

    investigations = {
        canonicalize_candidate_url(item.get("requested_url") or "")
        or str(item.get("requested_url") or ""): item
        for item in result.get("candidate_investigations") or []
    }
    browser_evidence = {
        canonicalize_candidate_url(item.get("requested_url") or "")
        or str(item.get("requested_url") or ""): item
        for item in result.get("browser_evidence") or []
    }
    assessments = {
        canonicalize_candidate_url(item.get("url") or "") or str(item.get("url") or ""): item
        for item in result.get("feature_assessments") or []
    }
    evidence_set = result.get("evidence_set") or {}
    review_urls = {
        canonicalize_candidate_url(url) or url
        for url in evidence_set.get("selected_urls") or []
    }
    primary_url = canonicalize_candidate_url(result.get("primary_url") or "")

    records: list[dict[str, Any]] = []
    for index, (url, candidate) in enumerate(candidates.items(), start=1):
        admission = admissions.get(url, {})
        scrape = scrapes.get(url, {})
        verification = verifications.get(url, {})
        scorecard = scorecards.get(url, {})
        investigation = investigations.get(url, {})
        browser = browser_evidence.get(url, {})
        assessment = assessments.get(url, {})
        browser_admission = browser_admissions.get(url, {})
        utility = _utility(scrape, verification) if scrape else {
            "fetch_success": False,
            "content_extracted": False,
            "product_page_likelihood": 0.0,
            "content_utility_score": 0.0,
            "scrape_accepted": False,
        }
        evidence = assessment.get("evidence") or []
        supported = [
            item
            for item in evidence
            if str(item.get("status"))
            in {"STRUCTURED_FOUND", "EXPLICITLY_FOUND", "LLM_FOUND"}
        ]
        selected = bool(primary_url and url == primary_url)
        review_selected = url in review_urls
        browser_admitted = bool(browser_admission.get("admitted")) or url in investigations
        browser_openable = _bool(browser.get("browser_openable"))
        coverage = _float(assessment.get("coverage"))
        identity_status = str(
            assessment.get("identity_status")
            or verification.get("identity_status")
            or "NOT_SCRAPED"
        )
        admission_reason = str(admission.get("admission_reason") or "NOT_EVALUATED")
        record: dict[str, Any] = {
            "candidate_id": investigation.get("candidate_id") or f"URL-{index:03d}",
            "canonical_url": url,
            "url": url,
            "requested_url": candidate.get("url") or url,
            "final_url": browser.get("final_url") or scrape.get("final_url") or url,
            "domain": candidate.get("domain") or domain_of(url),
            "search_stages": _compact(
                item.removeprefix("scope_")
                for item in candidate.get("source_types") or []
                if str(item).startswith("scope_")
            ),
            "source_types": _compact(candidate.get("source_types")),
            "appearance_count": int(candidate.get("organic_count") or 0),
            "best_position": candidate.get("best_position") or "",
            "serp_title": candidate.get("title") or "",
            "serp_snippet": candidate.get("snippet") or "",
            "url_type": admission.get("url_type") or "UNKNOWN",
            "preflight_score": _float(admission.get("preflight_score")),
            "identity_overlap": _float(admission.get("identity_overlap")),
            "admitted_for_scrape": _bool(admission.get("admitted_for_scrape")),
            "admission_reason": admission_reason,
            "full_scrape_attempted": bool(scrape),
            **utility,
            "scrapable": _bool(scrape.get("is_scrapable")),
            "richness": _float(scrape.get("richness_score")),
            "identity_status": identity_status,
            "ean_check": verification.get("ean_check") or "UNKNOWN",
            "title_check": verification.get("title_check") or "UNKNOWN",
            "variant_status": verification.get("variant_check") or "UNKNOWN",
            "page_type": verification.get("page_type_check") or "UNKNOWN",
            "validation_status": scorecard.get("validation_status") or "NOT_EVALUATED",
            "confidence": _float(scorecard.get("final_confidence")),
            "feature_evidence_count": len(supported),
            "coverage": coverage,
            "missing_features": _compact(assessment.get("missing_features")),
            "conflicting_features": _compact(assessment.get("conflicting_features")),
            "browser_admitted": browser_admitted,
            "browser_admission_reason": browser_admission.get("reason") or "",
            "browser_turns": int(investigation.get("turns_used") or 0),
            "browser_actions": int(investigation.get("actions_executed") or 0),
            "browser_outcome": investigation.get("termination_reason") or "NOT_RUN",
            "browser_openable": browser_openable,
            "selected": selected,
            "review_selected": review_selected,
            "decision_reasons": _compact(
                [
                    *(scorecard.get("hard_failures") or []),
                    *(scorecard.get("soft_warnings") or []),
                    *(assessment.get("rejection_reasons") or []),
                    admission_reason,
                ]
            ),
        }
        record["final_status"] = _final_status(
            selected=selected,
            review_selected=review_selected,
            admission_reason=admission_reason,
            scrape_attempted=bool(scrape),
            fetch_success=record["fetch_success"],
            scrape_accepted=record["scrape_accepted"],
            identity_status=identity_status,
            browser_admitted=browser_admitted,
            browser_openable=browser_openable,
            coverage=coverage,
        )
        record["rejection_category"] = (
            "NONE" if selected else record["final_status"]
        )
        for item in evidence:
            feature_key = _safe_feature(
                str(item.get("feature_id") or item.get("feature_name") or "feature")
            )
            record[f"feature_{feature_key}_value"] = item.get("value")
            record[f"feature_{feature_key}_status"] = item.get("status")
            record[f"feature_{feature_key}_confidence"] = _float(item.get("confidence"))
        records.append(record)

    canonical_urls = [item["canonical_url"] for item in records]
    if len(canonical_urls) != len(set(canonical_urls)):
        raise RuntimeError("candidate record contract violated: canonical_url must be unique")
    return sorted(
        records,
        key=lambda item: (
            bool(item.get("selected")),
            bool(item.get("review_selected")),
            bool(item.get("scrape_accepted")),
            _float(item.get("confidence")),
        ),
        reverse=True,
    )


def write_candidate_records(root: Path, records: list[dict[str, Any]]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "candidate_url_records.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    fieldnames: list[str] = []
    for record in records:
        for key in record:
            if key not in fieldnames:
                fieldnames.append(key)
    with (root / "candidates.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record)
