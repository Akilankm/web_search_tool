from __future__ import annotations

from pathlib import Path
from typing import Any

from src.product_evidence_harness.structured_no_url_outcome import (
    NO_URL_DELIVERY_STATUS,
    NO_URL_OUTCOME_CODE,
    is_structured_no_url_outcome,
)


def augment_no_url_business_review(
    result: dict[str, Any],
    artifact_root: Path,
) -> None:
    """Make the human review explicit and internally consistent for no-URL runs."""

    if not is_structured_no_url_outcome(result):
        return

    review = result.get("business_judgement_review")
    if not isinstance(review, dict):
        return

    steps = review.get("steps")
    if isinstance(steps, list) and steps:
        final = dict(steps[-1])
        final.update(
            {
                "decision_stage": "FINAL_NO_SAFE_URL_REVIEW_OUTCOME",
                "business_question": (
                    "What should the system return when bounded search finds no safe direct product page?"
                ),
                "agent_judgement": (
                    "No safe direct product URL was found. The run is preserved as REVIEW_REQUIRED "
                    "with a complete audit trail; no URL was fabricated or promoted from an indirect page."
                ),
                "judgement_status": "REVIEW_REQUIRED",
                "alternative_rejected": (
                    "Fabricated URLs, search-result pages, category pages, social pages, documents, "
                    "and unverified indirect references."
                ),
                "rejection_reason": NO_URL_OUTCOME_CODE,
                "business_rule_applied": (
                    "Search exhaustion is a controlled business no-match outcome, not an internal exception. "
                    "Preserve the trace and require human review rather than inventing a URL."
                ),
                "effect_on_next_action": (
                    "Review the search stages, verify identifiers and optionally provide a retailer or known "
                    "candidate before approving a broader search policy."
                ),
                "confidence": "deterministic no-fabrication policy",
                "final_outcome": NO_URL_DELIVERY_STATUS,
            }
        )
        steps[-1] = final
        review["steps"] = steps
        review["judgement_count"] = len(steps)

    review["human_review_status"] = "PENDING_NO_URL_RESOLUTION_REVIEW"
    review["no_url_outcome"] = result.get("resolution_outcome") or {}

    path_value = review.get("artifact_path")
    path = Path(str(path_value)) if path_value else artifact_root / "business_judgement_review.md"
    if not path.is_file():
        return

    existing = path.read_text(encoding="utf-8")
    banner = "\n".join(
        [
            "> **CONTROLLED NO-URL REVIEW OUTCOME**",
            ">",
            "> The bounded search completed without a safe direct external product-page URL. This is not a successful URL resolution and not an unhandled software exception. The system preserved the full trace, refused to fabricate a URL, and returned `REVIEW_REQUIRED` for human action.",
            "",
            "## No-safe-URL resolution summary",
            "",
            f"- **Outcome code:** `{NO_URL_OUTCOME_CODE}`",
            f"- **Delivery status:** `{NO_URL_DELIVERY_STATUS}`",
            f"- **SerpAPI credits used:** `{(result.get('resolution_outcome') or {}).get('serpapi_requests_used')}`",
            "- **URL delivered:** `False`",
            "- **URL fabricated:** `False`",
            "- **Required action:** review identifiers, search stages and rejected candidates before widening the search policy.",
            "",
        ]
    )
    marker = "# Business Judgment Review — Product URL Identification\n"
    if marker in existing:
        updated = existing.replace(marker, marker + "\n" + banner, 1)
    else:
        updated = banner + "\n" + existing
    path.write_text(updated, encoding="utf-8")
