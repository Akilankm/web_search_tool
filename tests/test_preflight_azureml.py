from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("preflight_azureml", ROOT / "scripts" / "preflight_azureml.py")
assert SPEC and SPEC.loader
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def valid_env() -> str:
    return "\n".join(
        [
            "SERPAPI_API_KEY=serpapi_key_with_more_than_twenty_chars",
            "PRODUCT_HARNESS_WORKFLOW=one_credit_feature_aware",
            "PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES=1",
            "PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES=0",
            "PRODUCT_HARNESS_ENABLE_VISION_REASONING=true",
            "PRODUCT_HARNESS_ENABLE_LLM_FEATURE_REASONING=false",
            "LLM_API_KEY=llm_key_with_more_than_sixteen_chars",
            "LLM_API_VERSION=2025-01-01-preview",
            "LLM_ENDPOINT=https://approved.example.net/",
            "LLM_DEPLOYMENT=vision-deployment",
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


def test_preflight_rejects_placeholder_credentials(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(valid_env().replace("serpapi_key_with_more_than_twenty_chars", "replace_with_real_serpapi_key"), encoding="utf-8")
    env_path.chmod(0o600)
    with pytest.raises(preflight.PreflightError, match="SERPAPI_API_KEY"):
        preflight.validate_env(preflight.parse_env(env_path))


def test_preflight_creates_and_validates_generic_feature_set(tmp_path: Path) -> None:
    example = tmp_path / "examples" / "features_to_code.example.json"
    example.parent.mkdir(parents=True)
    example.write_text(json.dumps({"features_to_code": ["feature one"]}), encoding="utf-8")

    files = preflight.ensure_feature_set(tmp_path)

    assert files == [tmp_path / "inputs" / "private" / "example_features.json"]
    preflight.validate_feature_file(files[0])


def test_preflight_rejects_invalid_feature_contract(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"features": ["wrong key"]}), encoding="utf-8")
    with pytest.raises(preflight.PreflightError, match="features_to_code"):
        preflight.validate_feature_file(path)
