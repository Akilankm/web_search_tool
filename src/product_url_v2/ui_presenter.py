from __future__ import annotations

from typing import Any, Mapping, Sequence

from product_url_v2.trace import TRACE_CONTRACT, TRACE_NOTICE

STAGE_ORDER = ("INTERPRET", "SEARCH", "ACQUIRE", "EVALUATE", "BROWSER", "DELIVER", "COMPLETE")
TERMINAL_STATUSES = {"COMPLETED", "REVIEW_REQUIRED", "FAILED", "TECHNICAL_FAILURE"}
SUCCESSFUL_TERMINAL_STATUSES = {"COMPLETED", "REVIEW_REQUIRED", "FAILED"}


def merge_events(existing: Sequence[Mapping[str, Any]], incoming: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged = {int(item.get("sequence") or 0): dict(item) for item in existing if int(item.get("sequence") or 0) > 0}
    for item in incoming:
        sequence = int(item.get("sequence") or 0)
        if sequence > 0:
            merged[sequence] = dict(item)
    return [merged[key] for key in sorted(merged)]


def stage_rows(events: Sequence[Mapping[str, Any]], current_stage: str, status: str) -> list[dict[str, str]]:
    completed = {
        str(item.get("stage") or "")
        for item in events
        if str(item.get("event_type") or "").upper() in {"COMPLETE", "DECISION_COMPLETE"}
    }
    started = {str(item.get("stage") or "") for item in events}
    rows = []
    for stage in STAGE_ORDER:
        if stage in completed or (stage == "COMPLETE" and status in SUCCESSFUL_TERMINAL_STATUSES):
            state = "COMPLETE"
        elif stage == current_stage:
            state = "ACTIVE"
        elif stage in started:
            state = "OBSERVED"
        else:
            state = "PENDING"
        rows.append({"stage": stage, "state": state})
    return rows


def signal_rows(interpretation: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    return [dict(item) for item in (interpretation or {}).get("signals") or []]


def hypothesis_rows(interpretation: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    for item in (interpretation or {}).get("hypotheses") or []:
        rows.append(
            {
                "hypothesis_id": item.get("hypothesis_id"),
                "canonical_name": item.get("canonical_name"),
                "probability": item.get("prior_probability"),
                "attributes": ", ".join(f"{key}={value}" for key, value in (item.get("attributes") or {}).items()),
                "negative_constraints": "; ".join(item.get("negative_constraints") or []),
                "rationale": item.get("rationale"),
            }
        )
    return rows


def search_rows(observations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for observation in observations:
        action = observation.get("action") or {}
        for result in observation.get("results") or []:
            rows.append(
                {
                    "credit": action.get("credit_number"),
                    "purpose": action.get("purpose"),
                    "engine": action.get("engine"),
                    "scope": action.get("scope"),
                    "position": result.get("position"),
                    "product_like": result.get("product_like"),
                    "title": result.get("title"),
                    "source_section": result.get("source_section"),
                    "url": result.get("url"),
                }
            )
    return rows


def candidate_rows(candidates: Sequence[Mapping[str, Any]], selected_candidate_id: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for item in candidates:
        rows.append(
            {
                "selected": item.get("candidate_id") == selected_candidate_id,
                "candidate": item.get("candidate_id"),
                "identity": item.get("identity_match"),
                "identity_confidence": item.get("identity_confidence"),
                "direct_page": item.get("direct_product_page"),
                "direct_page_score": item.get("direct_page_score"),
                "durable": item.get("durable_url"),
                "country": item.get("country_match"),
                "retailer": item.get("retailer_match"),
                "browser": item.get("browser_access"),
                "extractable": item.get("text_extractable"),
                "coding": item.get("coding_evidence_complete"),
                "source": item.get("source_role"),
                "authority": item.get("source_authority"),
                "conflicts": "; ".join(item.get("conflicts") or []),
                "url": item.get("url"),
            }
        )
    return rows


def event_rows(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "sequence": item.get("sequence"),
            "stage": item.get("stage"),
            "event_type": item.get("event_type"),
            "message": item.get("message"),
        }
        for item in events
    ]


__all__ = [
    "STAGE_ORDER",
    "TERMINAL_STATUSES",
    "TRACE_CONTRACT",
    "TRACE_NOTICE",
    "candidate_rows",
    "event_rows",
    "hypothesis_rows",
    "merge_events",
    "search_rows",
    "signal_rows",
    "stage_rows",
]
