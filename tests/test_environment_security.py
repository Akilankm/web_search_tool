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
            "PRODUCT_HARNESS_WORKFLOW=one_credit_feature_aware",
            "PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE=false",
            "PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES=1",
            "PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES=0",
            "PRODUCT_HARNESS_SERP_RESULTS=100",
            "PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING=false",
            "PRODUCT_HARNESS_ENABLE_LLM_SEARCH_FEEDBACK=false",
            "PRODUCT_HARNESS_ENABLE_LLM_FEATURE_REASONING=false",
            "",
        ]
    )


def test_valid_environment_returns_secret_free_report(tmp_path: Path) -> None:
    env_file = _write_env(tmp_path / ".env", _base_env())

    report = validate_runtime_environment(env_file, environ={})

    rendered = str(report.to_dict())
    assert report.serpapi_configured is True
    assert report.one_credit_contract_enforced is True
    assert "serp_live_" not in rendered


def test_placeholder_serpapi_key_is_rejected(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path / ".env",
        _base_env().replace("serp_live_abcdefghijklmnopqrstuvwxyz0123456789", "replace_with_real_serpapi_key"),
    )

    with pytest.raises(EnvironmentValidationError, match="placeholder"):
        validate_runtime_environment(env_file, environ={})


def test_unsafe_search_expansion_is_rejected(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path / ".env",
        _base_env().replace("PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE=false", "PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE=true"),
    )

    with pytest.raises(EnvironmentValidationError, match="forbids"):
        validate_runtime_environment(env_file, environ={})


def test_llm_enabled_requires_secure_complete_configuration(tmp_path: Path) -> None:
    env_file = _write_env(
        tmp_path / ".env",
        _base_env().replace(
            "PRODUCT_HARNESS_ENABLE_LLM_FEATURE_REASONING=false",
            "PRODUCT_HARNESS_ENABLE_LLM_FEATURE_REASONING=true",
        ),
    )

    with pytest.raises(EnvironmentValidationError, match="LLM_API_KEY"):
        validate_runtime_environment(env_file, environ={})


def test_duplicate_keys_are_rejected(tmp_path: Path) -> None:
    env_file = _write_env(tmp_path / ".env", _base_env() + "SERPAPI_API_KEY=second_value_that_must_not_win\n")

    with pytest.raises(EnvironmentValidationError, match="Duplicate"):
        validate_runtime_environment(env_file, environ={})


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits are required")
def test_group_readable_env_file_is_rejected(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(_base_env(), encoding="utf-8")
    env_file.chmod(0o644)

    with pytest.raises(EnvironmentValidationError, match="chmod 600"):
        validate_runtime_environment(env_file, environ={})
