from __future__ import annotations

from src.product_evidence_harness.url_delivery_summary import (
    attach_url_delivery_summary,
)


_PATCHED = False


def apply_executive_summary_patch() -> None:
    """Attach the URL-delivery-first summary to every completed agent result."""

    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    from src.product_evidence_harness.agent_service.strict_orchestrator import (
        StrictProductEvidenceOrchestrator,
    )

    current_run = StrictProductEvidenceOrchestrator.run
    if getattr(current_run, "_executive_summary_wrapper", False):
        return

    def run(self, payload, *, progress=None):
        result = current_run(self, payload, progress=progress)
        return attach_url_delivery_summary(result)

    run._executive_summary_wrapper = True
    StrictProductEvidenceOrchestrator.run = run
