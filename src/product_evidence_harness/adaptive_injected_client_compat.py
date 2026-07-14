from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.product_evidence_harness.serp_clients import GoogleOrganicSearchClient
from src.product_evidence_harness.three_stage_pipeline import ThreeStageProductEvidenceHarness


_pre_adaptive_run: Callable[..., Any] | None = None


def capture_pre_adaptive_run() -> None:
    """Capture the precision-gated fixed-search runner before adaptive patching.

    Production construction uses ``GoogleOrganicSearchClient`` and therefore the
    adaptive multi-engine runtime. A few library consumers and unit fixtures
    inject a custom organic client that implements only ``search``. Those clients
    cannot execute Shopping, AI Mode, Lens or token-expansion actions, so they
    retain the prior fixed three-call compatibility behavior unless they also
    inject an explicit adaptive planner or router.
    """

    global _pre_adaptive_run
    _pre_adaptive_run = ThreeStageProductEvidenceHarness.run


def install_injected_client_compatibility() -> None:
    if _pre_adaptive_run is None:
        raise RuntimeError("capture_pre_adaptive_run must run before adaptive patching")
    if getattr(ThreeStageProductEvidenceHarness, "_injected_client_compat_applied", False):
        return

    adaptive_run = ThreeStageProductEvidenceHarness.run
    fixed_run = _pre_adaptive_run

    def run(self, *args, **kwargs):
        explicit_adaptive_dependencies = bool(
            getattr(self, "adaptive_search_router", None)
            or getattr(self, "adaptive_search_planner", None)
        )
        default_client = isinstance(self.organic_client, GoogleOrganicSearchClient)
        if not default_client and not explicit_adaptive_dependencies:
            return fixed_run(self, *args, **kwargs)
        return adaptive_run(self, *args, **kwargs)

    ThreeStageProductEvidenceHarness.run = run
    ThreeStageProductEvidenceHarness._injected_client_compat_applied = True
