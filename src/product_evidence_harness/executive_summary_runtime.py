from __future__ import annotations

from src.product_evidence_harness.executive_summary import attach_executive_summary


_PATCHED = False


def apply_executive_summary_patch() -> None:
    """Attach the decision-first URL summary to every completed agent result."""

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
        return attach_executive_summary(result)

    run._executive_summary_wrapper = True
    StrictProductEvidenceOrchestrator.run = run
