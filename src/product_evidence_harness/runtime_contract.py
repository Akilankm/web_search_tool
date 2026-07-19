from __future__ import annotations

# Increment this whenever notebook/agent/bootstrap compatibility changes in a
# way that requires rebuilding the Docker agent image.
# Previous contract: belief-url-resolution-v5-manufacturer-primary
RUNTIME_CONTRACT_VERSION = "belief-url-resolution-v6-business-judgement-review"

REQUIRED_RUNTIME_CAPABILITIES = {
    "belief_driven_product_resolution": "belief-driven product resolution",
    "mandatory_review_url_delivery": "mandatory review URL delivery",
    "deterministic_browser_fallback_on_llm_error": "deterministic browser fallback",
    "notebook_self_healing_runtime": "notebook self-healing runtime",
    "compatibility_patches_applied": "agent compatibility-patch bootstrap",
    "manufacturer_first_primary_url": "manufacturer-first primary URL selection",
    "business_judgement_review_artifact": "human-comparable business judgment review artifact",
}

# These fields must exist and contain values in every completed or
# review-required orchestrated response.
REQUIRED_RESULT_FIELDS = (
    "product_identification",
    "search.market_decision_path",
    "url_delivery",
    "primary_url_role",
    "source_selection",
    "business_judgement_review",
)

# These keys are part of the stable response schema but may legitimately be
# null when the corresponding qualified source was not found.
REQUIRED_RESULT_KEYS = (
    "manufacturer_url",
    "retailer_url",
)


def runtime_capabilities() -> dict[str, object]:
    return {
        "runtime_contract_version": RUNTIME_CONTRACT_VERSION,
        **{key: True for key in REQUIRED_RUNTIME_CAPABILITIES},
    }
