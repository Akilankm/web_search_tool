from __future__ import annotations

from typing import Any, Mapping


_PATCHED = False


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def apply_url_delivery_summary_patch() -> None:
    """Install mandatory review-URL recovery and URL-first summaries."""

    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    from src.product_evidence_harness.url_delivery_enforcement_runtime import (
        apply_url_delivery_enforcement_patch,
    )

    apply_url_delivery_enforcement_patch()

    from src.product_evidence_harness import executive_summary

    original = executive_summary.build_executive_summary
    if getattr(original, "_url_delivery_first_summary", False):
        return

    def build(result: Mapping[str, Any]) -> dict[str, Any]:
        summary = original(result)
        selected_url = str(summary.get("selected_url") or "").strip()
        delivery = _mapping(result.get("url_delivery"))
        recovery = _mapping(result.get("url_delivery_recovery"))
        strict = bool(summary.get("strictly_verified"))

        summary["delivery_obligation"] = "MANDATORY"
        summary["successful_output"] = bool(selected_url)
        summary["url_recovery_used"] = bool(recovery)
        summary["url_recovery"] = recovery

        if selected_url and strict:
            summary["overall_status"] = "URL_DELIVERED_VERIFIED"
            summary["headline"] = "Product URL delivered"
        elif selected_url:
            summary["overall_status"] = "URL_DELIVERED_REVIEW_REQUIRED"
            summary["headline"] = "Product URL delivered — review recommended"
            summary["conclusion"] = (
                f"The strongest real direct product URL was delivered for {summary.get('product_name') or 'the identified product'}. "
                "It did not pass every strict production gate, so the URL is marked for review rather than withheld."
            )
        else:
            summary["overall_status"] = "URL_DELIVERY_FAILED"
            summary["headline"] = "URL delivery failed — escalation required"
            summary["conclusion"] = (
                "This run did not deliver the required product URL and is not a successful output. "
                "No non-mismatched direct external product-page candidate remained after the complete search and recovery route."
            )
            summary["successful_output"] = False
            summary["delivery_failure"] = {
                "status": delivery.get("status") or "NO_DIRECT_PRODUCT_URL_AVAILABLE",
                "exceptional": True,
                "requires_escalation": True,
            }

        pillars = _mapping(summary.get("pillars"))
        source = _mapping(pillars.get("source"))
        usability = _mapping(pillars.get("usability"))
        if selected_url:
            source["status"] = "DELIVERED_VERIFIED" if strict else "DELIVERED_FOR_REVIEW"
            usability["status"] = "READY" if strict else "REVIEW_REQUIRED"
        else:
            source["status"] = "DELIVERY_FAILED"
            usability["status"] = "DELIVERY_FAILED"
        pillars["source"] = source
        pillars["usability"] = usability
        summary["pillars"] = pillars
        return summary

    build._url_delivery_first_summary = True
    executive_summary.build_executive_summary = build
