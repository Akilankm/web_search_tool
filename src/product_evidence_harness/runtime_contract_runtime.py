from __future__ import annotations

from src.product_evidence_harness.runtime_contract import RUNTIME_CONTRACT_VERSION


_PATCHED = False


def apply_runtime_contract_patch() -> None:
    """Expose the agent image contract so notebooks reject stale containers."""

    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    from src.product_evidence_harness.agent_service.orchestrator import (
        ProductEvidenceOrchestrator,
    )

    original_health = ProductEvidenceOrchestrator.health

    def health(self):
        result = dict(original_health(self))
        result["runtime_contract_version"] = RUNTIME_CONTRACT_VERSION
        result["belief_driven_product_resolution"] = True
        result["mandatory_review_url_delivery"] = True
        result["deterministic_browser_fallback_on_llm_error"] = True
        return result

    ProductEvidenceOrchestrator.health = health
