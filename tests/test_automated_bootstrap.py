from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


preflight = load_script("bootstrap_preflight", ROOT / "scripts" / "preflight_azureml.py")
waiter = load_script("bootstrap_waiter", ROOT / "scripts" / "wait_for_stack.py")


def test_auto_permission_mode_repairs_normal_filesystem(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("KEY=value\n", encoding="utf-8")
    env_path.chmod(0o777)

    allow, policy = preflight.prepare_env_permissions(env_path, mode="auto")

    assert allow is False
    assert policy == "strict-0600"
    assert env_path.stat().st_mode & 0o077 == 0


def test_auto_permission_mode_allows_only_cloudfiles_when_chmod_cannot_fix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_path = tmp_path / "cloudfiles" / "code" / ".env"
    env_path.parent.mkdir(parents=True)
    env_path.write_text("KEY=value\n", encoding="utf-8")
    env_path.chmod(0o777)

    monkeypatch.setattr(Path, "chmod", lambda self, mode: None)
    monkeypatch.setattr(preflight, "is_azureml_cloudfiles_path", lambda path: True)

    allow, policy = preflight.prepare_env_permissions(env_path, mode="auto")

    assert allow is True
    assert policy == "azureml-managed-mount-auto-fallback"


def test_startup_detects_resolved_azureml_mount_path() -> None:
    source = (ROOT / "scripts" / "azureml_startup.sh").read_text(encoding="utf-8").lower()

    assert "/cloudfiles/" in source
    assert "/mnt/batch/tasks/shared/ls_root/mounts/" in source
    assert "is_azureml_managed_workspace" in source
    assert 'env_permission_mode="allow"' in source


def test_startup_supports_deterministic_clean_build_recovery() -> None:
    source = (ROOT / "scripts" / "azureml_startup.sh").read_text(encoding="utf-8")

    assert "--clean-build" in source
    assert "CLEAN_BUILD=true" in source
    assert "docker compose build --no-cache agent browser" in source
    assert "--force-recreate" in source
    assert "Runtime contract:" in source
    assert "--clean-build and --no-build cannot be used together" in source


def test_preflight_accepts_azure_openai_aliases() -> None:
    values = {
        "SERPAPI_API_KEY": "serpapi_key_with_more_than_twenty_chars",
        "PRODUCT_HARNESS_WORKFLOW": "three_stage_feature_aware",
        "PRODUCT_HARNESS_MAX_SERPAPI_CREDITS": "3",
        "PRODUCT_HARNESS_ALLOWED_SEARCH_ENGINES": (
            "google,google_shopping,google_ai_mode,"
            "google_immersive_product,google_lens"
        ),
        "PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING": "true",
        "PRODUCT_HARNESS_ENABLE_LLM_SEARCH_FEEDBACK": "true",
        "PRODUCT_HARNESS_REQUIRE_LLM_SEARCH_PLANNING": "true",
        "PRODUCT_HARNESS_EARLY_STOP_ON_WORKING_URL": "true",
        "PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES": "3",
        "PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES": "0",
        "PRODUCT_HARNESS_COUNTRY_FIRST": "true",
        "PRODUCT_HARNESS_ALLOW_GLOBAL_FALLBACK": "true",
        "PRODUCT_HARNESS_ENABLE_BROWSER_SERVICE": "true",
        "PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER": "true",
        "PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER": "true",
        "PRODUCT_HARNESS_REQUIRE_ALL_FEATURES_ON_PRIMARY": "true",
        "PRODUCT_HARNESS_REJECT_EXPIRING_URLS": "true",
        "AZURE_OPENAI_API_KEY": "x",
        "AZURE_OPENAI_API_VERSION": "internal-v1",
        "AZURE_OPENAI_ENDPOINT": "enterprise-gateway/service/openai",
        "AZURE_OPENAI_DEPLOYMENT": "vision model / production",
    }

    preflight.validate_env(values)


def test_waiter_extracts_nested_agent_configuration_error() -> None:
    payload = {
        "detail": {
            "status": "unhealthy",
            "configuration_error": "ValueError: Missing LLM configuration",
        }
    }
    assert waiter.extract_configuration_error(payload) == "ValueError: Missing LLM configuration"


def test_waiter_rejects_legacy_runtime_contract() -> None:
    payload = {
        "status": "healthy",
        "runtime_contract_version": "missing/legacy",
    }
    error = waiter.runtime_contract_error(payload)
    assert error is not None
    assert "runtime contract mismatch" in error.lower()


def test_waiter_accepts_current_runtime_contract() -> None:
    from src.product_evidence_harness.runtime_contract import runtime_capabilities

    assert waiter.runtime_contract_error({"status": "healthy", **runtime_capabilities()}) is None


def test_waiter_parses_env_without_exposing_values(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text('AGENT_HOST_PORT="9999"\nSECRET=hidden\n', encoding="utf-8")
    values = waiter.parse_env_file(env_path)
    assert values["AGENT_HOST_PORT"] == "9999"
    assert values["SECRET"] == "hidden"


def test_notebook_and_runtime_contain_bootstrap_and_feature_discovery_contract() -> None:
    notebook = json.loads(
        (ROOT / "notebooks" / "01_run_product_evidence.ipynb").read_text(
            encoding="utf-8"
        )
    )
    source = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"]
    )
    runtime = (
        ROOT / "src" / "product_evidence_harness" / "notebook_runtime.py"
    ).read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "./scripts/azureml_startup.sh" in readme
    assert 'project_root / "data" / "artifacts"' in runtime
    assert "RUN_SINGLE_PRODUCT = False" in source
    assert "Available feature sets" in source
    assert "Default feature set" in source
    assert "adaptive_search_contract_enforced" in runtime
    assert "ensure_platform_ready" in source
    assert "AUTO_RECOVER_PLATFORM = True" in source
