from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]


def test_env_example_exists_and_enforces_adaptive_three_credit_contract() -> None:
    path = ROOT / ".env.example"
    assert path.is_file()
    values = dotenv_values(path)

    assert values["PRODUCT_HARNESS_WORKFLOW"] == "three_stage_feature_aware"
    assert values["PRODUCT_HARNESS_MAX_SERPAPI_CREDITS"] == "3"
    assert values["PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES"] == "3"
    assert values["PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES"] == "0"
    assert values["PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING"] == "true"
    assert values["PRODUCT_HARNESS_ENABLE_LLM_SEARCH_FEEDBACK"] == "true"
    assert values["PRODUCT_HARNESS_REQUIRE_LLM_SEARCH_PLANNING"] == "true"
    assert values["PRODUCT_HARNESS_EARLY_STOP_ON_WORKING_URL"] == "true"
    engines = {
        item.strip()
        for item in str(values["PRODUCT_HARNESS_ALLOWED_SEARCH_ENGINES"]).split(",")
    }
    assert {
        "google",
        "google_shopping",
        "google_ai_mode",
        "google_immersive_product",
        "google_lens",
    }.issubset(engines)
    assert values["PRODUCT_HARNESS_BROWSER_FALLBACK_ONLY"] == "false"
    assert values["PRODUCT_HARNESS_ENABLE_BROWSER_SERVICE"] == "true"
    assert values["PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER"] == "true"
    assert values["PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER"] == "true"
    assert (
        values["PRODUCT_HARNESS_ALLOW_DETERMINISTIC_BROWSER_FALLBACK_ON_LLM_ERROR"]
        == "true"
    )
    assert values["PRODUCT_HARNESS_ENABLE_VISION_REASONING"] == "true"
    assert values["PRODUCT_HARNESS_COUNTRY_FIRST"] == "true"
    assert values["PRODUCT_HARNESS_ALLOW_GLOBAL_FALLBACK"] == "true"
    assert values["PRODUCT_HARNESS_REQUIRE_ALL_FEATURES_ON_PRIMARY"] == "true"
    assert values["PRODUCT_HARNESS_REJECT_EXPIRING_URLS"] == "true"
    assert values["PRODUCT_HARNESS_NOTEBOOK_AUTO_RECOVER_PLATFORM"] == "true"
    assert values["PRODUCT_HARNESS_NOTEBOOK_CLEAN_BUILD_ON_RECOVERY"] == "true"
    assert int(values["PRODUCT_HARNESS_BROWSER_CANDIDATE_LIMIT"]) >= 1
    assert 1 <= int(values["PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES"]) <= 90
    assert 1 <= int(values["PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE"]) <= 30
    assert 1 <= int(values["PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE"]) <= 60


def test_env_example_uses_placeholders_not_live_secrets() -> None:
    values = dotenv_values(ROOT / ".env.example")
    assert str(values["SERPAPI_API_KEY"]).startswith("replace_with_")
    assert str(values["LLM_API_KEY"]).startswith("replace_with_")
    assert str(values["LLM_ENDPOINT"]).startswith("replace_with_")
    assert str(values["LLM_DEPLOYMENT"]).startswith("replace_with_")


def test_gitignore_blocks_runtime_secrets_and_private_inputs() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines() if line.strip()}
    assert ".env" in lines
    assert ".env.*" in lines
    assert "!.env.example" in lines
    assert "secrets/" in lines
    assert "inputs/private/*" in lines
    assert "!inputs/private/toy_features.json" in lines
