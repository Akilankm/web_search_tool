from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.product_evidence_harness.demo_runtime_options import (
    ContextAwareEnvironment,
    current_demo_runtime_options,
    demo_runtime_option_scope,
    effective_demo_runtime_options,
    runtime_option_catalog,
)


_PATCHED = False


def _write_run_configuration(result: dict[str, Any]) -> None:
    root_value = result.get("artifact_dir")
    if not root_value:
        return
    root = Path(str(root_value))
    root.mkdir(parents=True, exist_ok=True)

    for name, payload in (
        ("run_configuration.json", result.get("run_configuration") or {}),
        ("orchestrated_result.json", result),
    ):
        path = root / name
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)


def _annotate_result(result: dict[str, Any]) -> dict[str, Any]:
    requested = current_demo_runtime_options()
    effective = effective_demo_runtime_options()
    result["run_configuration"] = {
        "mode": "PER_JOB_DEMO_OVERRIDE" if requested else "ENVIRONMENT_DEFAULTS",
        "requested_runtime_options": requested,
        "effective_runtime_options": effective,
        "option_catalog": runtime_option_catalog(),
        "safety_contract": {
            "credentials_exposed": False,
            "environment_file_mutated": False,
            "shared_container_restarted": False,
            "identity_gates_changeable": False,
            "url_durability_gate_changeable": False,
            "no_fabrication_policy_changeable": False,
        },
    }

    search = dict(result.get("search") or {})
    search.update(
        {
            "serpapi_request_limit": effective["serpapi_credits"],
            "maximum_full_scrapes": effective["full_scrapes"],
            "maximum_scrapes_per_domain": effective["scrapes_per_domain"],
            "planner_candidate_context_limit": effective["planner_candidates"],
        }
    )
    result["search"] = search

    browser = dict(result.get("agentic_browser") or {})
    browser.update(
        {
            "max_candidates": effective["agentic_candidates"],
            "max_turns_per_candidate": effective["browser_turns_per_candidate"],
            "max_actions_per_candidate": effective["browser_actions_per_candidate"],
            "max_images_in_reasoning": effective["images_in_reasoning"],
        }
    )
    result["agentic_browser"] = browser

    outcome = result.get("resolution_outcome")
    if isinstance(outcome, dict):
        outcome["serpapi_request_limit"] = effective["serpapi_credits"]
        result["resolution_outcome"] = outcome

    _write_run_configuration(result)
    return result


def apply_demo_runtime_options_patch() -> None:
    """Install per-job budgets without mutating process-wide environment variables."""

    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    from src.product_evidence_harness import adaptive_search_runtime
    from src.product_evidence_harness.agent_service import strict_orchestrator
    from src.product_evidence_harness.llm import agentic_browser

    adaptive_search_runtime.os = ContextAwareEnvironment(adaptive_search_runtime.os)
    strict_orchestrator.os = ContextAwareEnvironment(strict_orchestrator.os)
    agentic_browser.os = ContextAwareEnvironment(agentic_browser.os)

    current_run = strict_orchestrator.StrictProductEvidenceOrchestrator.run

    def run(self, payload, *, progress=None):
        raw_options = payload.get("runtime_options") if isinstance(payload, dict) else None
        with demo_runtime_option_scope(raw_options):
            result = current_run(self, payload, progress=progress)
            return _annotate_result(result)

    strict_orchestrator.StrictProductEvidenceOrchestrator.run = run
