from __future__ import annotations

from dataclasses import replace


_PATCHED = False


def apply_belief_compatibility_patch() -> None:
    """Preserve stable public trace labels around the new belief runtime."""

    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    from src.product_evidence_harness.three_stage_pipeline import (
        ThreeStageProductEvidenceHarness,
    )

    current_build_stage = ThreeStageProductEvidenceHarness._build_stage

    def build_stage(self, product, state, stage_index):
        stage = current_build_stage(self, product, state, stage_index)
        if (
            not product.retailer_name
            and stage_index == 0
            and stage.name == "country_alternative"
        ):
            return replace(stage, name="country_primary")
        return stage

    ThreeStageProductEvidenceHarness._build_stage = build_stage
