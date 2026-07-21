from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from src.product_evidence_harness.demo_runtime_options import (
    ContextAwareEnvironment,
    default_demo_runtime_options,
    demo_runtime_option_scope,
    normalize_demo_runtime_options,
)
from src.product_evidence_harness.demo_runtime_options_runtime import (
    _annotate_result,
    apply_demo_runtime_options_patch,
)


def test_demo_runtime_options_are_narrow_and_bounded() -> None:
    defaults = default_demo_runtime_options()
    assert defaults["serpapi_credits"] == 3
    assert defaults["agentic_candidates"] == 3

    assert normalize_demo_runtime_options(
        {
            "serpapi_credits": 2,
            "full_scrapes": 5,
            "browser_turns_per_candidate": 6,
        }
    ) == {
        "serpapi_credits": 2,
        "full_scrapes": 5,
        "browser_turns_per_candidate": 6,
    }

    with pytest.raises(ValueError, match="Unsupported runtime option"):
        normalize_demo_runtime_options({"disable_identity_gate": True})
    with pytest.raises(ValueError, match="between 1 and 3"):
        normalize_demo_runtime_options({"serpapi_credits": 4})
    with pytest.raises(ValueError, match="not a boolean"):
        normalize_demo_runtime_options({"full_scrapes": True})


def test_context_aware_environment_does_not_mutate_process_environment(monkeypatch) -> None:
    import os

    monkeypatch.setenv("PRODUCT_HARNESS_MAX_SERPAPI_CREDITS", "3")
    proxy = ContextAwareEnvironment(os)

    assert proxy.getenv("PRODUCT_HARNESS_MAX_SERPAPI_CREDITS") == "3"
    with demo_runtime_option_scope({"serpapi_credits": 1}):
        assert proxy.getenv("PRODUCT_HARNESS_MAX_SERPAPI_CREDITS") == "1"
        assert os.getenv("PRODUCT_HARNESS_MAX_SERPAPI_CREDITS") == "3"
    assert proxy.getenv("PRODUCT_HARNESS_MAX_SERPAPI_CREDITS") == "3"


def test_concurrent_jobs_keep_independent_search_budgets() -> None:
    apply_demo_runtime_options_patch()
    from src.product_evidence_harness import adaptive_search_runtime

    barrier = Barrier(2)

    def read_budget(value: int) -> int:
        with demo_runtime_option_scope({"serpapi_credits": value}):
            barrier.wait(timeout=10)
            return adaptive_search_runtime._bounded_int(
                "PRODUCT_HARNESS_MAX_SERPAPI_CREDITS",
                3,
                1,
                3,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(read_budget, (1, 3)))

    assert values == [1, 3]


def test_result_records_effective_budget_and_writes_artifact(tmp_path: Path) -> None:
    result = {
        "artifact_dir": str(tmp_path),
        "search": {"serpapi_requests_used": 1},
        "agentic_browser": {"candidate_urls_admitted": 1},
    }
    requested = {
        "serpapi_credits": 2,
        "full_scrapes": 4,
        "scrapes_per_domain": 1,
        "planner_candidates": 7,
        "agentic_candidates": 2,
        "browser_turns_per_candidate": 3,
        "browser_actions_per_candidate": 5,
        "images_in_reasoning": 6,
    }

    with demo_runtime_option_scope(requested):
        annotated = _annotate_result(result)

    assert annotated["run_configuration"]["mode"] == "PER_JOB_DEMO_OVERRIDE"
    assert annotated["run_configuration"]["requested_runtime_options"] == requested
    assert annotated["search"]["serpapi_request_limit"] == 2
    assert annotated["search"]["maximum_full_scrapes"] == 4
    assert annotated["agentic_browser"]["max_candidates"] == 2
    assert annotated["agentic_browser"]["max_images_in_reasoning"] == 6
    assert annotated["run_configuration"]["safety_contract"] == {
        "credentials_exposed": False,
        "environment_file_mutated": False,
        "shared_container_restarted": False,
        "identity_gates_changeable": False,
        "url_durability_gate_changeable": False,
        "no_fabrication_policy_changeable": False,
    }

    configuration_path = tmp_path / "run_configuration.json"
    result_path = tmp_path / "orchestrated_result.json"
    assert configuration_path.is_file()
    assert result_path.is_file()
    persisted = json.loads(configuration_path.read_text(encoding="utf-8"))
    assert persisted["effective_runtime_options"]["serpapi_credits"] == 2
