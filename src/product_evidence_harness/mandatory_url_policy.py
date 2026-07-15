from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse

from src.product_evidence_harness.candidate_precision import (
    canonicalize_candidate_url,
    classify_candidate_url,
)
from src.product_evidence_harness.constants import (
    IDENTITY_UNVERIFIED,
    VALIDATION_NEEDS_REVIEW,
)
from src.product_evidence_harness.contracts import CandidateScorecard
from src.product_evidence_harness.selector import FinalSelector
from src.product_evidence_harness.source_authority import source_tier
from src.product_evidence_harness.url_utils import domain_of


_BLOCKED_URL_TYPES = {
    "DOCUMENT_OR_MEDIA",
    "SOCIAL_OR_COMMUNITY",
    "HOMEPAGE",
    "SEARCH_RESULTS",
    "CATEGORY_OR_COLLECTION",
}
_BLOCKED_INTERMEDIARY_DOMAINS = {
    "google.com",
    "googleusercontent.com",
    "googleadservices.com",
    "serpapi.com",
}


def _direct_external_url(value: str | None) -> str | None:
    canonical = canonicalize_candidate_url(str(value or ""))
    if not canonical:
        return None
    parsed = urlparse(canonical)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host or any(host == item or host.endswith("." + item) for item in _BLOCKED_INTERMEDIARY_DOMAINS):
        return None
    if classify_candidate_url(canonical) in _BLOCKED_URL_TYPES:
        return None
    return canonical


def _card_rank(card: CandidateScorecard) -> tuple[float, ...]:
    scrape = card.scrape
    verification = card.verification
    url = _direct_external_url(card.candidate.url)
    if not url:
        return (-1.0,)
    identity_verified = bool(
        verification
        and verification.identity_status == "VERIFIED"
        and verification.variant_check != "CONFLICT"
    )
    llm_exact = card.llm_decision in {"EXACT_MATCH", "EXACT_MATCH_WITH_WARNING"}
    reachable = bool(scrape and scrape.reachable)
    scraped = bool(scrape and scrape.scraped and scrape.success)
    scrapable = bool(scrape and scrape.is_scrapable)
    product_page = bool(scrape and scrape.looks_like_product_page)
    return (
        float(identity_verified),
        float(llm_exact),
        float(not card.hard_failures),
        float(100 - source_tier(card.candidate)),
        float(product_page),
        float(scrapable),
        float(reachable),
        float(scraped),
        float(card.richness_score or 0.0),
        float(card.final_confidence or 0.0),
        float(-(card.candidate.best_position or 999)),
    )


def _strongest_deliverable_card(scorecards: Sequence[CandidateScorecard]) -> CandidateScorecard | None:
    ranked = sorted(
        (card for card in scorecards if _direct_external_url(card.candidate.url)),
        key=_card_rank,
        reverse=True,
    )
    return ranked[0] if ranked else None


def _deliverable_match(match, card: CandidateScorecard):
    url = _direct_external_url(card.candidate.url)
    if not url:
        return match
    scrape = card.scrape
    verification = card.verification
    hard_failures = tuple(card.hard_failures)
    warnings = tuple(dict.fromkeys((*card.soft_warnings, *hard_failures)))
    justification_parts = [
        "A real direct product-page candidate is mandatory for every completed product run.",
        "This URL is the strongest available candidate after the complete adaptive search budget.",
    ]
    if hard_failures:
        justification_parts.append("Strict acceptance warnings: " + "; ".join(hard_failures))
    return replace(
        match,
        product_url=url,
        best_available_url=url,
        best_reference_url=url,
        verified_exact_url=(url if match.is_exact_product_match else match.verified_exact_url),
        url_decision_status="MANDATORY_BEST_AVAILABLE_PRODUCT_URL",
        resolution_status="BEST_AVAILABLE_URL_DELIVERED",
        validation_status=(match.validation_status if match.is_exact_product_match else VALIDATION_NEEDS_REVIEW),
        identity_status=(verification.identity_status if verification else match.identity_status or IDENTITY_UNVERIFIED),
        match_reason="MANDATORY_PRODUCT_URL_DELIVERY",
        justification=" ".join(justification_parts),
        needs_review=not match.is_exact_product_match,
        selected_with_warning=not match.is_exact_product_match,
        primary_reject_reason=(match.primary_reject_reason or "STRICT_PRIMARY_ACCEPTANCE_NOT_MET"),
        reference_url_status="DELIVERED_BEST_AVAILABLE_PRODUCT_URL",
        hard_failures=hard_failures,
        soft_warnings=warnings,
        confidence=float(card.final_confidence or match.confidence or 0.0),
        is_scrapable=bool(scrape and scrape.is_scrapable),
        scrape_status_code=(scrape.status_code if scrape else match.scrape_status_code),
        scrape_word_count=(scrape.word_count if scrape else match.scrape_word_count),
        scrape_markdown_chars=(scrape.markdown_chars if scrape else match.scrape_markdown_chars),
        scrape_final_url=(scrape.final_url if scrape else url),
        richness_score=float(scrape.richness_score if scrape else card.richness_score or 0.0),
        selected_domain=domain_of(url),
    )


def _candidate_urls_from_result(result: dict[str, Any]) -> Iterable[str]:
    yield str(result.get("primary_url") or "")
    product_match = result.get("product_match") or {}
    for key in ("product_url", "best_available_url", "best_reference_url", "scrape_final_url"):
        yield str(product_match.get(key) or "")
    evidence_set = result.get("evidence_set") or {}
    yield str(evidence_set.get("primary_url") or "")
    for key in ("selected_urls", "supplementary_urls"):
        for value in evidence_set.get(key) or ():
            yield str(value or "")
    for value in result.get("supplementary_urls") or ():
        yield str(value or "")
    for item in result.get("feature_assessments") or ():
        yield str((item or {}).get("url") or "")
    for item in result.get("browser_evidence") or ():
        item = item or {}
        yield str(item.get("final_url") or "")
        yield str(item.get("requested_url") or "")


def _first_deliverable_url(result: dict[str, Any]) -> str | None:
    seen: set[str] = set()
    for value in _candidate_urls_from_result(result):
        url = _direct_external_url(value)
        if url and url not in seen:
            return url
        if url:
            seen.add(url)
    return None


def _write_result_artifacts(result: dict[str, Any]) -> None:
    root_value = result.get("artifact_dir")
    if not root_value:
        return
    root = Path(str(root_value))
    if not root.is_dir():
        return
    for name in ("orchestrated_result.json", "result.json"):
        path = root / name
        if path.is_file() or name == "orchestrated_result.json":
            path.write_text(
                json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
    acceptance = result.get("primary_url_acceptance") or {}
    (root / "primary_url_acceptance.json").write_text(
        json.dumps(acceptance, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _enforce_orchestrated_delivery(result: dict[str, Any]) -> dict[str, Any]:
    url = _first_deliverable_url(result)
    if not url:
        raise RuntimeError(
            "MANDATORY_PRODUCT_URL_NOT_FOUND: the adaptive search exhausted all SerpAPI credits "
            "without producing any direct external product-page candidate."
        )

    acceptance = dict(result.get("primary_url_acceptance") or {})
    strict_accepted = bool(acceptance.get("accepted"))
    acceptance["primary_url"] = url
    acceptance["delivery_required"] = True
    acceptance["delivery_status"] = (
        "STRICT_VERIFIED_PRODUCT_URL" if strict_accepted else "BEST_AVAILABLE_REVIEW_URL"
    )
    result["primary_url_acceptance"] = acceptance
    result["primary_url"] = url

    product_match = dict(result.get("product_match") or {})
    product_match["product_url"] = url
    product_match["best_available_url"] = url
    product_match.setdefault("best_reference_url", url)
    product_match["url_delivery_required"] = True
    product_match["url_delivery_status"] = acceptance["delivery_status"]
    if not strict_accepted:
        product_match["validation_status"] = VALIDATION_NEEDS_REVIEW
        product_match["resolution_status"] = "BEST_AVAILABLE_URL_DELIVERED"
        product_match["url_decision_status"] = "MANDATORY_BEST_AVAILABLE_PRODUCT_URL"
        product_match["needs_review"] = True
        product_match["selected_with_warning"] = True
        product_match["match_reason"] = "MANDATORY_PRODUCT_URL_DELIVERY"
    result["product_match"] = product_match

    evidence_set = dict(result.get("evidence_set") or {})
    existing = [str(item) for item in evidence_set.get("selected_urls") or () if item]
    selected = list(dict.fromkeys([url, *existing]))
    evidence_set["primary_url"] = url
    evidence_set["selected_urls"] = selected
    evidence_set["supplementary_urls"] = [item for item in selected[1:] if item != url]
    evidence_set["url_delivery_required"] = True
    if not strict_accepted:
        evidence_set["status"] = "REVIEW_REQUIRED_WITH_PRODUCT_URL"
        evidence_set["coding_ready"] = False
    result["evidence_set"] = evidence_set
    result["supplementary_urls"] = evidence_set["supplementary_urls"]
    result["url_delivery"] = {
        "required": True,
        "delivered": True,
        "url": url,
        "strictly_verified": strict_accepted,
        "status": acceptance["delivery_status"],
        "empty_url_is_success": False,
    }
    if not strict_accepted:
        result["job_status"] = "REVIEW_REQUIRED"
        result["coding_ready"] = False
    _write_result_artifacts(result)
    return result


def apply_mandatory_product_url_policy() -> None:
    if getattr(FinalSelector, "_mandatory_url_policy_applied", False):
        return

    original_select = FinalSelector.select

    def select(self, *, task, scorecards, termination_reason, budget_snapshot, llm_calls_used=0, state=None):
        match = original_select(
            self,
            task=task,
            scorecards=scorecards,
            termination_reason=termination_reason,
            budget_snapshot=budget_snapshot,
            llm_calls_used=llm_calls_used,
            state=state,
        )
        if _direct_external_url(match.product_url):
            return match
        card = _strongest_deliverable_card(scorecards)
        return _deliverable_match(match, card) if card is not None else match

    FinalSelector.select = select

    from src.product_evidence_harness.agent_service.strict_orchestrator import (
        StrictProductEvidenceOrchestrator,
    )

    original_run = StrictProductEvidenceOrchestrator.run

    def run(self, payload, *, progress=None):
        return _enforce_orchestrated_delivery(original_run(self, payload, progress=progress))

    StrictProductEvidenceOrchestrator.run = run
    FinalSelector._mandatory_url_policy_applied = True
