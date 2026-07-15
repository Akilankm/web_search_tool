from __future__ import annotations

import os
from pathlib import Path

import pytest

from product_evidence_harness import EnvironmentValidationError, validate_runtime_environment


def _write_env(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o600)
    return path


def _base_env() -> str:
    return "\n".join(
        [
            "SERPAPI_API_KEY=serp_live_abcdefghijklmnopqrstuvwxyz0123456789",
            "PRODUCT_HARNESS_WORKFLOW=three_stage_feature_aware",
            "PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE=false",
            "PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=3",
            "PRODUCT_HARNESS_ALLOWED_SEARCH_ENGINES=google,google_shopping,google_ai_mode,google_immersive_product,google_lens,amazon,ebay,walmart,home_depot",
            "PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING=true",
            "PRODUCT_HARNESS_ENABLE_LLM_SEARCH_FEEDBACK=true",
            "PRODUCT_HARNESS_REQUIRE_LLM_SEARCH_PLANNING=true",
            "PRODUCT_HARNESS_EARLY_STOP_ON_WORKING_URL=true",
            "PRODUCT_HARNESS_SEARCH_PLANNER_MAX_CANDIDATES=8",
            "PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES=3",
            "PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES=0",
            "PRODUCT_HARNESS_SERP_RESULTS=100",
            "PRODUCT_HARNESS_ENABLE_LLM_FEATURE_REASONING=false",
            "PRODUCT_HARNESS_LLM_MAX_CALLS_PER_PRODUCT=6",
            "PRODUCT_HARNESS_COUNTRY_FIRST=true",
            "PRODUCT_HARNESS_ALLOW_GLOBAL_FALLBACK=true",
            "PRODUCT_HARNESS_ENABLE_BROWSER_SERVICE=true",
            "PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER=true",
            "PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER=true",
            "PRODUCT_HARNESS_REQUIRE_ALL_FEATURES_ON_PRIMARY=true",
            "PRODUCT_HARNESS_REJECT_EXPIRING_URLS=true",
            "PRODUCT_HARNESS_MAX_FULL_SCRAPES=6",
            "PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN=2",
            "PRODUCT_HARNESS_MIN_PREFLIGHT_SCORE=0.28",
            "PRODUCT_HARNESS_SCRAPE_TOP_K_PER_STAGE=2",
            "PRODUCT_HARNESS_BROWSER_CANDIDATE_LIMIT=18",
            "PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES=18",
            "PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE=10",
            "PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE=20",
            "PRODUCT_HARNESS_AGENTIC_OBSERVATION_CHARS=12000",
            "PRODUCT_HARNESS_AGENTIC_MAX_ELEMENTS=60",
            "PRODUCT_HARNESS_AGENTIC_MAX_IMAGES=30",
            "LLM_API_KEY=llm_key_abcdefghijklmnopqrstuvwxyz",
            "LLM_API_VERSION=2025-01-01-preview",
            "LLM_ENDPOINT=https://approved.company.net/",
            "LLM_DEPLOYMENT=vision-deployment",
            "",
        ]
    )


def test_valid_environment_returns_secret_free_adaptive_report(tmp_path: Path) -> None:
    env_file = _write_env(tmp_path / ".env", _base_env())

    report = validate_runtime_environment(env_file, environ={})

    rendered = str(report.to_dict())
    assert report.serpapi_configured is True
    assert report.one_credit_contract_enforced is False
    assert report.three_stage_contract_enforced is True
    assert report.adaptive_search_contract_enforced is True
    assert report.serpapi_request_limit == 3
    assert report.llm_search_planning_enabled is True
    assert report.llm_search_feedback_enabled is True
    assert report.max_llm_calls_per_product == 6
    assert "adaptive_llm_call_budget_validated" in report.checks_passed
    assert "google_shopping" in report.allowed_search_engines
    assert "google_immersive_product" in report.allowed_search_engines
    assert report.agentic_browser_enabled is True
    assert report.agentic_browser_required is True
    assert report.agentic_browser_contract_enforced is True
    assert report.llm_configured is True
    assert report.max_agentic_candidates == 3
    assert report.max_agentic_turns_per_candidate == 4
    assert report.max_agentic_actions_per_candidate == 6
    assert "serp_live_" not in rendered
    assert "llm_key_" not in rendered


def test_adaptive_llm_call_budget_above_six_is_rejected(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path / ".env",
        _base_env().replace(
            "PRODUCT_HARNESS_LLM_MAX_CALLS_PER_PRODUCT=6",
            "PRODUCT_HARNESS_LLM_MAX_CALLS_PER_PRODUCT=7",
        ),
    )
    with pytest.raises(EnvironmentValidationError, match="between 0 and 6"):
        validate_runtime_environment(env_file, environ={})


def test_placeholder_serpapi_key_is_rejected(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path / ".env",
        _base_env().replace(
            "serp_live_abcdefghijklmnopqrstuvwxyz0123456789",
            "replace_with_real_serpapi_key",
        ),
    )
    with pytest.raises(EnvironmentValidationError, match="placeholder"):
        validate_runtime_environment(env_file, environ={})


def test_expansive_legacy_search_mode_is_rejected(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path / ".env",
        _base_env().replace(
            "PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE=false",
            "PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE=true",
        ),
    )
    with pytest.raises(EnvironmentValidationError, match="forbids"):
        validate_runtime_environment(env_file, environ={})


def test_search_budget_must_be_exactly_three(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path / ".env",
        _base_env().replace(
            "PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=3",
            "PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=2",
        ),
    )
    with pytest.raises(EnvironmentValidationError, match="between 3 and 3"):
        validate_runtime_environment(env_file, environ={})


def test_llm_search_planning_cannot_be_disabled(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path / ".env",
        _base_env().replace(
            "PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING=true",
            "PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING=false",
        ),
    )
    with pytest.raises(EnvironmentValidationError, match="requires LLM search planning"):
        validate_runtime_environment(env_file, environ={})


def test_strict_acceptance_flags_cannot_be_disabled(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path / ".env",
        _base_env().replace(
            "PRODUCT_HARNESS_REQUIRE_ALL_FEATURES_ON_PRIMARY=true",
            "PRODUCT_HARNESS_REQUIRE_ALL_FEATURES_ON_PRIMARY=false",
        ),
    )
    with pytest.raises(EnvironmentValidationError, match="must be true"):
        validate_runtime_environment(env_file, environ={})


def test_agentic_browser_cannot_be_disabled(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path / ".env",
        _base_env().replace(
            "PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER=true",
            "PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER=false",
        ),
    )
    with pytest.raises(EnvironmentValidationError, match="must be true"):
        validate_runtime_environment(env_file, environ={})


def test_search_planner_requires_complete_llm_configuration(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path / ".env",
        _base_env().replace(
            "LLM_API_KEY=llm_key_abcdefghijklmnopqrstuvwxyz",
            "LLM_API_KEY=",
        ),
    )
    with pytest.raises(EnvironmentValidationError, match="LLM_API_KEY"):
        validate_runtime_environment(env_file, environ={})


def test_duplicate_keys_are_rejected(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path / ".env",
        _base_env() + "SERPAPI_API_KEY=second_value_that_must_not_win\n",
    )
    with pytest.raises(EnvironmentValidationError, match="Duplicate"):
        validate_runtime_environment(env_file, environ={})


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits are required")
def test_group_readable_env_file_is_rejected(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(_base_env(), encoding="utf-8")
    env_file.chmod(0o644)
    with pytest.raises(EnvironmentValidationError, match="chmod 600"):
        validate_runtime_environment(env_file, environ={})
