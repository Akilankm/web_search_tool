from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "preflight_azureml",
    ROOT / "scripts" / "preflight_azureml.py",
)
assert SPEC and SPEC.loader
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def valid_env() -> str:
    return "\n".join(
        [
            "SERPAPI_API_KEY=serpapi_key_with_more_than_twenty_chars",
            "PRODUCT_HARNESS_WORKFLOW=three_stage_feature_aware",
            "PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=3",
            "PRODUCT_HARNESS_ALLOWED_SEARCH_ENGINES=google,google_shopping,google_ai_mode,google_immersive_product,google_lens,amazon,ebay,walmart,home_depot",
            "PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING=true",
            "PRODUCT_HARNESS_ENABLE_LLM_SEARCH_FEEDBACK=true",
            "PRODUCT_HARNESS_REQUIRE_LLM_SEARCH_PLANNING=true",
            "PRODUCT_HARNESS_EARLY_STOP_ON_WORKING_URL=true",
            "PRODUCT_HARNESS_SEARCH_PLANNER_MAX_CANDIDATES=8",
            "PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES=3",
            "PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES=0",
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
            "PRODUCT_HARNESS_BROWSER_CANDIDATE_LIMIT=3",
            "PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES=3",
            "PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE=4",
            "PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE=6",
            "PRODUCT_HARNESS_AGENTIC_OBSERVATION_CHARS=4000",
            "PRODUCT_HARNESS_AGENTIC_MAX_ELEMENTS=15",
            "PRODUCT_HARNESS_AGENTIC_MAX_IMAGES=8",
            "PRODUCT_HARNESS_ENABLE_VISION_REASONING=true",
            "PRODUCT_HARNESS_ENABLE_LLM_FEATURE_REASONING=false",
            "LLM_API_KEY=enterprise-key",
            "LLM_API_VERSION=enterprise-version",
            "LLM_ENDPOINT=enterprise-gateway",
            "LLM_DEPLOYMENT=enterprise-deployment",
            "AGENT_HOST_PORT=8788",
            "",
        ]
    )


def test_preflight_parses_valid_environment(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(valid_env(), encoding="utf-8")
    env_path.chmod(0o600)
    values = preflight.parse_env(env_path)
    preflight.validate_env(values)


def test_preflight_rejects_non_three_credit_budget(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        valid_env().replace(
            "PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=3",
            "PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=2",
        ),
        encoding="utf-8",
    )
    env_path.chmod(0o600)

    with pytest.raises(preflight.PreflightError, match="between 3 and 3"):
        preflight.validate_env(preflight.parse_env(env_path))


def test_preflight_rejects_disabled_llm_search_planner(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        valid_env().replace(
            "PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING=true",
            "PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING=false",
        ),
        encoding="utf-8",
    )
    env_path.chmod(0o600)

    with pytest.raises(preflight.PreflightError, match="must be true"):
        preflight.validate_env(preflight.parse_env(env_path))


def test_preflight_rejects_missing_core_engine(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        valid_env().replace(
            "google_ai_mode,",
            "",
        ),
        encoding="utf-8",
    )
    env_path.chmod(0o600)

    with pytest.raises(preflight.PreflightError, match="Missing required"):
        preflight.validate_env(preflight.parse_env(env_path))


def test_preflight_rejects_disabled_strict_acceptance(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        valid_env().replace(
            "PRODUCT_HARNESS_REJECT_EXPIRING_URLS=true",
            "PRODUCT_HARNESS_REJECT_EXPIRING_URLS=false",
        ),
        encoding="utf-8",
    )
    env_path.chmod(0o600)

    with pytest.raises(preflight.PreflightError, match="must be true"):
        preflight.validate_env(preflight.parse_env(env_path))


def test_preflight_rejects_disabled_agentic_browser(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        valid_env().replace(
            "PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER=true",
            "PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER=false",
        ),
        encoding="utf-8",
    )
    env_path.chmod(0o600)

    with pytest.raises(preflight.PreflightError, match="must be true"):
        preflight.validate_env(preflight.parse_env(env_path))


def test_preflight_rejects_broad_permissions_by_default(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(valid_env(), encoding="utf-8")
    env_path.chmod(0o777)

    with pytest.raises(preflight.PreflightError, match="permissions are too broad"):
        preflight.parse_env(env_path)


def test_preflight_allows_broad_permissions_only_with_explicit_override(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(valid_env(), encoding="utf-8")
    env_path.chmod(0o777)

    values = preflight.parse_env(env_path, allow_insecure_permissions=True)

    assert values["SERPAPI_API_KEY"] == "serpapi_key_with_more_than_twenty_chars"
    assert "SECURITY WARNING" in capsys.readouterr().err


def test_process_permission_override_is_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(preflight.INSECURE_PERMISSION_OVERRIDE_ENV, raising=False)
    assert preflight.process_flag_enabled(preflight.INSECURE_PERMISSION_OVERRIDE_ENV) is False

    monkeypatch.setenv(preflight.INSECURE_PERMISSION_OVERRIDE_ENV, "true")
    assert preflight.process_flag_enabled(preflight.INSECURE_PERMISSION_OVERRIDE_ENV) is True


def test_preflight_rejects_placeholder_credentials(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        valid_env().replace(
            "serpapi_key_with_more_than_twenty_chars",
            "replace_with_real_serpapi_key",
        ),
        encoding="utf-8",
    )
    env_path.chmod(0o600)
    with pytest.raises(preflight.PreflightError, match="SERPAPI_API_KEY"):
        preflight.validate_env(preflight.parse_env(env_path))


def test_preflight_creates_and_validates_generic_feature_set(tmp_path: Path) -> None:
    example = tmp_path / "examples" / "features_to_code.example.json"
    example.parent.mkdir(parents=True)
    example.write_text(
        json.dumps({"features_to_code": ["feature one"]}),
        encoding="utf-8",
    )

    files = preflight.ensure_feature_set(tmp_path)

    assert files == [tmp_path / "inputs" / "private" / "example_features.json"]
    preflight.validate_feature_file(files[0])


def test_preflight_creates_repository_local_runtime_layout(tmp_path: Path) -> None:
    created = preflight.ensure_runtime_directories(tmp_path)

    assert created == (
        tmp_path / "data" / "artifacts",
        tmp_path / "data" / "runtime",
        tmp_path / "secrets",
    )
    assert all(path.is_dir() for path in created)
    assert not (tmp_path / "artifacts").exists()


def test_preflight_rejects_invalid_feature_contract(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"features": ["wrong key"]}), encoding="utf-8")
    with pytest.raises(preflight.PreflightError, match="features_to_code"):
        preflight.validate_feature_file(path)
