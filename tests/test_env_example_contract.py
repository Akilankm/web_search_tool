from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]


def test_env_example_exists_and_enforces_one_credit_contract() -> None:
    path = ROOT / ".env.example"
    assert path.is_file()
    values = dotenv_values(path)

    assert values["PRODUCT_HARNESS_WORKFLOW"] == "one_credit_feature_aware"
    assert values["PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES"] == "1"
    assert values["PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES"] == "0"
    assert values["PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING"] == "false"
    assert values["PRODUCT_HARNESS_ENABLE_LLM_SEARCH_FEEDBACK"] == "false"
    assert values["PRODUCT_HARNESS_BROWSER_FALLBACK_ONLY"] == "false"
    assert values["PRODUCT_HARNESS_ENABLE_BROWSER_SERVICE"] == "true"
    assert values["PRODUCT_HARNESS_ENABLE_VISION_REASONING"] == "true"


def test_env_example_uses_placeholders_not_live_secrets() -> None:
    values = dotenv_values(ROOT / ".env.example")
    assert str(values["SERPAPI_API_KEY"]).startswith("replace_with_")
    assert str(values["LLM_API_KEY"]).startswith("replace_with_")
    assert str(values["LLM_ENDPOINT"]).startswith("https://replace-")


def test_gitignore_blocks_runtime_secrets_and_private_inputs() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines() if line.strip()}
    assert ".env" in lines
    assert ".env.*" in lines
    assert "!.env.example" in lines
    assert "secrets/" in lines
    assert "inputs/private/" in lines
