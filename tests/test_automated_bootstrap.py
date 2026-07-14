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
    assert policy == "azureml-cloudfiles-auto-fallback"


def test_startup_detects_resolved_azureml_mount_path() -> None:
    source = (ROOT / "scripts" / "azureml_startup.sh").read_text(encoding="utf-8").lower()

    assert "/cloudfiles/" in source
    assert "/mnt/batch/tasks/shared/ls_root/mounts/" in source
    assert "is_azureml_managed_workspace" in source
    assert 'env_permission_mode="allow"' in source


def test_preflight_accepts_azure_openai_aliases() -> None:
    values = {
        "SERPAPI_API_KEY": "serpapi_key_with_more_than_twenty_chars",
        "PRODUCT_HARNESS_WORKFLOW": "three_stage_feature_aware",
        "PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES": "3",
        "PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES": "0",
        "PRODUCT_HARNESS_COUNTRY_FIRST": "true",
        "PRODUCT_HARNESS_ALLOW_GLOBAL_FALLBACK": "true",
        "PRODUCT_HARNESS_ENABLE_BROWSER_SERVICE": "true",
        "PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER": "true",
        "PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER": "true",
        "PRODUCT_HARNESS_REQUIRE_ALL_FEATURES_ON_PRIMARY": "true",
        "PRODUCT_HARNESS_REJECT_EXPIRING_URLS": "true",
        "AZURE_OPENAI_API_KEY": "real_enterprise_llm_key_value",
        "AZURE_OPENAI_API_VERSION": "2025-01-01-preview",
        "AZURE_OPENAI_ENDPOINT": "https://approved.company.net/",
        "AZURE_OPENAI_DEPLOYMENT": "vision-deployment",
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


def test_waiter_parses_env_without_exposing_values(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text('AGENT_HOST_PORT="9999"\nSECRET=hidden\n', encoding="utf-8")
    values = waiter.parse_env_file(env_path)
    assert values["AGENT_HOST_PORT"] == "9999"
    assert values["SECRET"] == "hidden"


def test_notebook_contains_bootstrap_and_feature_discovery_contract() -> None:
    notebook = json.loads((ROOT / "notebooks" / "01_run_product_evidence.ipynb").read_text(encoding="utf-8"))
    source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])

    assert "./scripts/azureml_startup.sh" in source
    assert 'PROJECT_ROOT / "data" / "runtime" / "stack_health.json"' in source
    assert "available_feature_sets" in source
    assert "RUN_SINGLE_PRODUCT = False" in source
    assert "Available FEATURE_SET values" in source
