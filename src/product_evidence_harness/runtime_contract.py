from __future__ import annotations

# Increment this whenever notebook/agent/bootstrap compatibility changes in a
# way that requires rebuilding the Docker agent image.
RUNTIME_CONTRACT_VERSION = "belief-url-resolution-v5-manufacturer-primary"

REQUIRED_RUNTIME_CAPABILITIES = {
    "belief_driven_product_resolution": "belief-driven product resolution",
    "mandatory_review_url_delivery": "mandatory review URL delivery",
    "deterministic_browser_fallback_on_llm_error": "deterministic browser fallback",
    "notebook_self_healing_runtime": "notebook self-healing runtime",
    "compatibility_patches_applied": "agent compatibility-patch bootstrap",
}

REQUIRED_RESULT_FIELDS = (
    "product_identification",
    "search.market_decision_path",
    "url_delivery",
)


def runtime_capabilities() -> dict[str, object]:
    return {
        "runtime_contract_version": RUNTIME_CONTRACT_VERSION,
        **{key: True for key in REQUIRED_RUNTIME_CAPABILITIES},
        "manufacturer_first_primary_url": True,
    }
