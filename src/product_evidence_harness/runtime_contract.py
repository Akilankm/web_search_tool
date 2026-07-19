from __future__ import annotations

# Increment this whenever the notebook/agent result contract or runtime patch
# topology changes in a way that requires rebuilding the Docker agent image.
RUNTIME_CONTRACT_VERSION = "belief-url-resolution-v2"

REQUIRED_RESULT_FIELDS = (
    "product_identification",
    "search.market_decision_path",
    "url_delivery",
)
