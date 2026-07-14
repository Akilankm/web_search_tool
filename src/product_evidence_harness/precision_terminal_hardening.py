from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _find_base_plan(function: Callable[..., Any]) -> Callable[..., Any]:
    """Recover the original class planner from compatibility wrapper closures."""
    seen: set[int] = set()

    def visit(value: Any) -> Callable[..., Any] | None:
        if not callable(value) or id(value) in seen:
            return None
        seen.add(id(value))
        if getattr(value, "__name__", "") == "_plan":
            return value
        for cell in getattr(value, "__closure__", ()) or ():
            try:
                nested = cell.cell_contents
            except ValueError:
                continue
            found = visit(nested)
            if found is not None:
                return found
        return None

    return visit(function) or function


def _resolved_feature_ids(history: list[dict[str, Any]]) -> set[str]:
    resolved: set[str] = set()
    for plan in history:
        assessment = plan.get("candidate_assessment") or {}
        resolved.update(
            str(item) for item in assessment.get("resolved_feature_ids") or []
        )
    return resolved


def _build_preserving_plan(base_plan: Callable[..., Any]):
    def plan(self, request, schema, observation, history):
        requested = {feature.feature_id for feature in schema.features}
        already_resolved = _resolved_feature_ids(history)
        if requested and requested.issubset(already_resolved):
            return {
                "action": "finish",
                "element_id": None,
                "direction": None,
                "reason": "Every requested feature is already resolved.",
                "termination_reason": "ALL_REQUESTED_FEATURES_RESOLVED",
                "candidate_assessment": history[-1].get(
                    "candidate_assessment", {}
                )
                if history
                else {},
            }

        value = base_plan(self, request, schema, observation, history)
        assessment = value.get("candidate_assessment") or {}
        if (
            assessment.get("same_product") is False
            or assessment.get("same_variant") is False
        ):
            value.update(
                {
                    "action": "finish",
                    "termination_reason": "IDENTITY_OR_VARIANT_REJECTED",
                    "reason": "The observed page is not the requested product or variant.",
                }
            )
            return value
        if assessment.get("product_page") is False:
            value.update(
                {
                    "action": "finish",
                    "termination_reason": "NON_PRODUCT_PAGE",
                    "reason": "The observed page is not an individual product detail page.",
                }
            )
            return value

        resolved = _resolved_feature_ids([*history, value])
        if requested and requested.issubset(resolved):
            # Preserve an explicit, valid LLM finish reason. The deterministic
            # completeness label is only injected when the model did not already
            # terminate the turn itself.
            existing_action = str(value.get("action") or "").strip().lower()
            existing_reason = str(value.get("termination_reason") or "").strip()
            if existing_action != "finish" or not existing_reason:
                value.update(
                    {
                        "action": "finish",
                        "termination_reason": "ALL_REQUESTED_FEATURES_RESOLVED",
                        "reason": "Every requested feature has grounded evidence.",
                    }
                )
        return value

    return plan


def apply_precision_terminal_hardening() -> None:
    from src.product_evidence_harness.llm.agentic_browser import (
        AgenticBrowserInvestigator,
    )

    if getattr(
        AgenticBrowserInvestigator,
        "_precision_terminal_hardening_applied",
        False,
    ):
        return
    base_plan = _find_base_plan(AgenticBrowserInvestigator._plan)
    AgenticBrowserInvestigator._plan = _build_preserving_plan(base_plan)
    AgenticBrowserInvestigator._precision_terminal_hardening_applied = True
