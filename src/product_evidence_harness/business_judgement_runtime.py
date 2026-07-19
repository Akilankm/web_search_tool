from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.product_evidence_harness.business_judgement_artifact import (
    ARTIFACT_FILENAME,
    write_business_judgement_review,
)


_PATCHED = False


def apply_business_judgement_review_patch() -> None:
    """Attach a human-comparable business-judgment artifact to every final run."""

    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    from src.product_evidence_harness.agent_service.strict_orchestrator import (
        StrictProductEvidenceOrchestrator,
    )

    current_run = StrictProductEvidenceOrchestrator.run

    def run(self, payload: dict[str, Any], *, progress=None):
        result = current_run(self, payload, progress=progress)
        artifact_value = result.get("artifact_dir")
        if not artifact_value:
            return result

        artifact_root = Path(str(artifact_value))
        artifact_root.mkdir(parents=True, exist_ok=True)
        review = write_business_judgement_review(result, artifact_root)

        result["business_judgement_review"]["artifact_filename"] = ARTIFACT_FILENAME
        result["business_judgement_review"]["human_review_status"] = (
            review.get("human_review_status") or "PENDING_HUMAN_COMPARISON"
        )
        (artifact_root / "orchestrated_result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        return result

    StrictProductEvidenceOrchestrator.run = run
