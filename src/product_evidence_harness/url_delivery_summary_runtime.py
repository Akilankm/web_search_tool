from __future__ import annotations

import sys


_PATCHED = False


def apply_url_delivery_summary_patch() -> None:
    """Install canonical URL delivery enforcement and summary functions."""

    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    from src.product_evidence_harness.url_delivery_enforcement_runtime import (
        apply_url_delivery_enforcement_patch,
    )
    from src.product_evidence_harness.url_delivery_summary import (
        attach_url_delivery_summary,
        build_url_delivery_summary,
    )
    from src.product_evidence_harness import executive_summary

    apply_url_delivery_enforcement_patch()

    executive_summary.build_executive_summary = build_url_delivery_summary
    executive_summary.attach_executive_summary = attach_url_delivery_summary

    sys.modules["product_evidence_harness.executive_summary"] = executive_summary
    package = sys.modules.get("product_evidence_harness")
    if package is not None:
        setattr(package, "executive_summary", executive_summary)
