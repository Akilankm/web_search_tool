from __future__ import annotations

from src.product_evidence_harness.runtime_contract import runtime_capabilities


_PATCHED = False


def apply_runtime_contract_patch() -> None:
    """Expose the agent image contract so notebooks can verify or recover it."""

    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    from src.product_evidence_harness.agent_service.orchestrator import (
        ProductEvidenceOrchestrator,
    )

    original_health = ProductEvidenceOrchestrator.health

    def health(self):
        return {**dict(original_health(self)), **runtime_capabilities()}

    ProductEvidenceOrchestrator.health = health
