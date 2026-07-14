from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from product_evidence_harness.environment import (
    EnvironmentValidationError,
    _validate_llm_environment,
)
from product_evidence_harness.llm.service import LLMConfig


ROOT = Path(__file__).resolve().parents[1]


def _load_preflight():
    path = ROOT / "scripts" / "preflight_azureml.py"
    spec = importlib.util.spec_from_file_location("enterprise_preflight", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _preflight_values() -> dict[str, str]:
    return {
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
        "LLM_API_KEY": "abc",
        "LLM_API_VERSION": "internal-v1",
        "LLM_ENDPOINT": "enterprise-gateway/service/openai",
        "LLM_DEPLOYMENT": "vision model / production",
    }


def test_llm_config_accepts_short_key_and_custom_endpoint() -> None:
    config = LLMConfig(
        api_key="abc",
        api_version="internal-v1",
        endpoint="enterprise-gateway/service/openai",
        deployment="vision model / production",
    )

    assert config.api_key == "abc"
    assert config.endpoint == "enterprise-gateway/service/openai"


def test_runtime_llm_validation_requires_presence_only() -> None:
    _validate_llm_environment(
        {
            "LLM_API_KEY": "x",
            "LLM_API_VERSION": "v",
            "LLM_ENDPOINT": "internal-gateway",
            "LLM_DEPLOYMENT": "model with spaces",
        }
    )


def test_preflight_accepts_enterprise_opaque_values() -> None:
    preflight = _load_preflight()
    preflight.validate_env(_preflight_values())


def test_required_llm_fields_are_still_required() -> None:
    values = _preflight_values()
    values["LLM_API_KEY"] = ""

    preflight = _load_preflight()
    with pytest.raises(preflight.PreflightError, match="Missing required LLM configuration"):
        preflight.validate_env(values)

    with pytest.raises(EnvironmentValidationError, match="Missing required LLM configuration"):
        _validate_llm_environment(
            {
                "LLM_API_KEY": "",
                "LLM_API_VERSION": "v",
                "LLM_ENDPOINT": "internal-gateway",
                "LLM_DEPLOYMENT": "model",
            }
        )
