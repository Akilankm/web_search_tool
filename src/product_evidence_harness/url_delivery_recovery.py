from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from src.product_evidence_harness.candidate_precision import (
    canonicalize_candidate_url,
    classify_candidate_url,
)


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
_REJECTED_IDENTITY_STATES = {
    "MISMATCH",
    "CONFLICT",
    "CONFLICTING",
    "IDENTITY_REJECTED",
    "WRONG_PRODUCT",
    "WRONG_VARIANT",
}
_REJECTED_FINAL_STATES = {
    "SERP_REJECTED_URL_TYPE",
    "IDENTITY_REJECTED",
    "NON_PRODUCT_PAGE",
}
_REJECTED_REASON_TOKENS = {
    "EAN_CONFLICT",
    "WRONG_EAN",
    "IDENTITY_MISMATCH",
    "VARIANT_CONFLICT",
    "WRONG_VARIANT",
    "WRONG_PRODUCT",
    "NON_PRODUCT_PAGE",
}
_URL_KEYS = {
    "url",
    "link",
    "product_url",
    "product_link",
    "merchant_link",
    "source_url",
    "canonical_url",
    "final_url",
    "requested_url",
}


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if number == number else default


def _truth(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "on", "verified", "pass"}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value or [] if isinstance(item, Mapping)]


def direct_external_product_url(value: Any) -> str | None:
    canonical = canonicalize_candidate_url(_text(value))
    if not canonical:
        return None
    parsed = urlparse(canonical)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host or any(
        host == blocked or host.endswith("." + blocked)
        for blocked in _BLOCKED_INTERMEDIARY_DOMAINS
    ):
        return None
    if classify_candidate_url(canonical) in _BLOCKED_URL_TYPES:
        return None
    return canonical


@dataclass(frozen=True)
class DeliveryCandidate:
    url: str
    origin: str
    score: float
    identity_status: str
    source_role: str
    source_tier: str
    final_status: str
    review_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _reason_tokens(record: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for key in (
        "decision_reasons",
        "rejection_reasons",
        "hard_failures",
        "conflicting_features",
        "admission_reason",
        "browser_outcome",
        "final_status",
    ):
        value = record.get(key)
        if isinstance(value, str):
            values.extend(part.strip() for part in value.replace("|", ";").split(";") if part.strip())
        elif isinstance(value, (list, tuple, set)):
            values.extend(_text(item) for item in value if _text(item))
    return tuple(dict.fromkeys(values))


def _confirmed_mismatch(record: Mapping[str, Any]) -> bool:
    identity = _text(
        record.get("identity_status")
        or record.get("identity")
        or record.get("resolution_status")
    ).upper()
    final_status = _text(record.get("final_status")).upper()
    page_type = _text(record.get("page_type") or record.get("url_type")).upper()
    reasons = " ".join(_reason_tokens(record)).upper()
    if identity in _REJECTED_IDENTITY_STATES:
        return True
    if final_status in _REJECTED_FINAL_STATES:
        return True
    if page_type in {"NON_PRODUCT_PAGE", "SEARCH_RESULTS", "CATEGORY_OR_COLLECTION", "HOMEPAGE"}:
        return True
    return any(token in reasons for token in _REJECTED_REASON_TOKENS)


def _candidate_score(record: Mapping[str, Any], *, origin: str, priority: float) -> float:
    identity = _text(record.get("identity_status") or record.get("identity")).upper()
    final_status = _text(record.get("final_status")).upper()
    source_role = _text(record.get("source_role") or record.get("primary_url_role")).upper()
    score = priority

    if _truth(record.get("selected")):
        score += 220
    if _truth(record.get("review_selected")):
        score += 150
    if final_status == "STRICT_SELECTED":
        score += 220
    elif final_status == "REVIEW_SELECTED":
        score += 150
    elif final_status == "ELIGIBLE_NOT_SELECTED":
        score += 80

    if identity in {"VERIFIED", "EXACT", "MATCH", "CONFIRMED"}:
        score += 180
    elif identity in {"PROBABLE", "LIKELY", "UNVERIFIED", "NOT_SCRAPED", ""}:
        score += 55

    if source_role in {"OFFICIAL_MANUFACTURER", "MANUFACTURER"}:
        score += 75
    elif "RETAILER" in source_role:
        score += 55

    if _truth(record.get("browser_openable")):
        score += 55
    if _truth(record.get("scrape_accepted")):
        score += 70
    if _truth(record.get("content_extracted")) or _truth(record.get("text_scrapable")):
        score += 45
    if _truth(record.get("fetch_success")):
        score += 30
    if _truth(record.get("admitted_for_scrape")):
        score += 20

    score += 65 * max(0.0, min(1.0, _number(record.get("product_page_likelihood"))))
    score += 55 * max(0.0, min(1.0, _number(record.get("confidence"))))
    score += 35 * max(0.0, min(1.0, _number(record.get("coverage"))))
    score += 20 * max(0.0, min(1.0, _number(record.get("preflight_score"))))

    position = _number(record.get("best_position"), 999.0)
    if position > 0:
        score += max(0.0, 20.0 - min(20.0, position))
    if origin.startswith("explicit"):
        score += 300
    return round(score, 6)


def _candidate_from_record(
    record: Mapping[str, Any],
    *,
    origin: str,
    priority: float,
) -> DeliveryCandidate | None:
    raw_url = next(
        (
            record.get(key)
            for key in (
                "final_url",
                "canonical_url",
                "product_url",
                "url",
                "requested_url",
                "link",
            )
            if record.get(key)
        ),
        None,
    )
    url = direct_external_product_url(raw_url)
    if not url or _confirmed_mismatch(record):
        return None
    return DeliveryCandidate(
        url=url,
        origin=origin,
        score=_candidate_score(record, origin=origin, priority=priority),
        identity_status=_text(record.get("identity_status") or record.get("identity"), "UNVERIFIED").upper(),
        source_role=_text(record.get("source_role") or record.get("primary_url_role"), "UNCLASSIFIED").upper(),
        source_tier=_text(record.get("source_tier_name") or record.get("source_tier"), "UNCLASSIFIED").upper(),
        final_status=_text(record.get("final_status"), "NOT_EVALUATED").upper(),
        review_reasons=_reason_tokens(record),
    )


def _explicit_records(result: Mapping[str, Any]) -> Iterable[tuple[dict[str, Any], str, float]]:
    acceptance = _mapping(result.get("primary_url_acceptance"))
    selection = _mapping(result.get("source_selection"))
    product_match = _mapping(result.get("product_match"))
    evidence_set = _mapping(result.get("evidence_set"))
    common = {
        "identity_status": product_match.get("identity_status"),
        "source_role": selection.get("source_role") or result.get("primary_url_role"),
        "source_tier_name": selection.get("source_tier_name"),
        "browser_openable": acceptance.get("browser_openable"),
        "text_scrapable": acceptance.get("text_scrapable"),
        "confidence": product_match.get("confidence"),
        "selected": True,
    }
    for key, value in (
        ("primary_url", result.get("primary_url")),
        ("product_url", product_match.get("product_url")),
        ("best_available_url", product_match.get("best_available_url")),
        ("best_reference_url", product_match.get("best_reference_url")),
        ("scrape_final_url", product_match.get("scrape_final_url")),
        ("evidence_primary", evidence_set.get("primary_url")),
    ):
        if value:
            yield ({"url": value, **common}, f"explicit:{key}", 700.0)
    for key in ("selected_urls", "supplementary_urls"):
        for value in evidence_set.get(key) or []:
            if value:
                yield ({"url": value, **common, "review_selected": True}, f"explicit:evidence_set.{key}", 620.0)
    for value in result.get("supplementary_urls") or []:
        if value:
            yield ({"url": value, **common, "review_selected": True}, "explicit:supplementary_urls", 610.0)


def _recursive_url_records(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, Mapping):
        record = dict(value)
        for key, item in record.items():
            if key in _URL_KEYS and isinstance(item, str) and item.startswith(("http://", "https://")):
                yield {**record, "url": item}
        for item in record.values():
            yield from _recursive_url_records(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _recursive_url_records(item)


def _artifact_records(result: Mapping[str, Any]) -> Iterable[tuple[dict[str, Any], str, float]]:
    root_value = _text(result.get("artifact_dir"))
    if not root_value:
        return
    root = Path(root_value)
    records_path = root / "candidate_url_records.json"
    if records_path.is_file():
        try:
            payload = json.loads(records_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = []
        for record in _records(payload):
            yield record, "artifact:candidate_url_records", 430.0

    state_path = root / "candidate_state.json"
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
        if isinstance(state, Mapping):
            admissions = {
                direct_external_product_url(item.get("canonical_url") or item.get("original_url")): item
                for item in _records(state.get("candidate_admissions"))
            }
            scrapes = {
                direct_external_product_url(url): _mapping(payload)
                for url, payload in _mapping(state.get("scrapes")).items()
            }
            verifications = {
                direct_external_product_url(url): _mapping(payload)
                for url, payload in _mapping(state.get("verifications")).items()
            }
            for candidate in _records(state.get("candidates")):
                url = direct_external_product_url(candidate.get("url"))
                if not url:
                    continue
                merged = {
                    **candidate,
                    **_mapping(admissions.get(url)),
                    **_mapping(scrapes.get(url)),
                    **_mapping(verifications.get(url)),
                    "url": url,
                }
                yield merged, "artifact:candidate_state", 300.0
            for record in _recursive_url_records(state.get("serp_results")):
                yield record, "artifact:serp_results", 170.0


def collect_delivery_candidates(result: Mapping[str, Any]) -> list[DeliveryCandidate]:
    raw: list[tuple[dict[str, Any], str, float]] = list(_explicit_records(result))
    raw.extend((record, "result:candidate_records", 450.0) for record in _records(result.get("candidate_records")))
    raw.extend((record, "result:feature_assessments", 390.0) for record in _records(result.get("feature_assessments")))
    raw.extend((record, "result:browser_evidence", 380.0) for record in _records(result.get("browser_evidence")))
    raw.extend((record, "result:candidate_investigations", 360.0) for record in _records(result.get("candidate_investigations")))
    raw.extend(
        (record, "result:serp_results", 150.0)
        for record in _recursive_url_records(_mapping(result.get("search")).get("serp_results"))
    )
    raw.extend(_artifact_records(result) or [])

    by_url: dict[str, DeliveryCandidate] = {}
    for record, origin, priority in raw:
        candidate = _candidate_from_record(record, origin=origin, priority=priority)
        if candidate is None:
            continue
        existing = by_url.get(candidate.url)
        if existing is None or candidate.score > existing.score:
            by_url[candidate.url] = candidate
    return sorted(by_url.values(), key=lambda item: (item.score, item.url), reverse=True)


def select_best_delivery_candidate(result: Mapping[str, Any]) -> DeliveryCandidate | None:
    candidates = collect_delivery_candidates(result)
    return candidates[0] if candidates else None


def apply_url_delivery_recovery_patch() -> None:
    from src.product_evidence_harness import mandatory_url_policy

    if getattr(mandatory_url_policy, "_url_delivery_recovery_applied", False):
        return

    original = mandatory_url_policy._first_deliverable_url

    def first_deliverable_url(result: dict[str, Any]) -> str | None:
        candidate = select_best_delivery_candidate(result)
        if candidate is not None:
            result["url_delivery_recovery"] = {
                "schema_version": "url-delivery-recovery-v1",
                "selected": candidate.to_dict(),
                "candidate_count": len(collect_delivery_candidates(result)),
                "policy": (
                    "Return the strongest real direct product URL that is not a confirmed product or variant mismatch. "
                    "Strictly verified URLs are preferred; otherwise deliver the best review URL."
                ),
            }
            return candidate.url
        return original(result)

    mandatory_url_policy._first_deliverable_url = first_deliverable_url
    mandatory_url_policy._url_delivery_recovery_applied = True
