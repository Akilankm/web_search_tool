from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from src.product_evidence_harness.artifact_diagnostics import (
    build_artifact_diagnostics,
    plot_artifact_mindmap,
    plot_business_judgement_timeline,
    resolve_artifact_dir,
    write_artifact_diagnostic_report,
)


def _write_artifact(root: Path) -> Path:
    artifact = root / "data" / "artifacts" / "ROW-1"
    artifact.mkdir(parents=True)
    result = {
        "job_status": "COMPLETED",
        "product": {
            "row_id": "ROW-1",
            "main_text": "Demo product",
            "ean": "00123",
            "retailer_name": None,
            "country_code": "CH",
            "language_code": "de",
        },
        "product_identification": {
            "resolution_status": "RESOLVED",
            "identified_product": "Demo Product Exact Variant",
        },
        "search": {
            "stages": [
                {
                    "serp_credit": 1,
                    "name": "manufacturer_primary",
                    "query": "Demo Product official",
                    "results_returned": 5,
                },
                {
                    "serp_credit": 2,
                    "name": "country_alternative",
                    "query": "Demo Product CH",
                    "results_returned": 4,
                },
            ]
        },
        "primary_url": "https://manufacturer.example/demo",
        "primary_url_role": "OFFICIAL_MANUFACTURER",
        "manufacturer_url": "https://manufacturer.example/demo",
        "retailer_url": "https://retailer.example/demo",
        "source_selection": {
            "selection_reason": "OFFICIAL_MANUFACTURER_PRIMARY_AFTER_STRICT_GATES"
        },
        "primary_url_acceptance": {"accepted": True},
        "url_delivery": {"delivered": True, "strictly_verified": True},
        "business_judgement_review": {
            "visual_evidence_summary": {
                "visual_assets_collected": 2,
                "screenshots_captured": 1,
                "image_influenced_final_decision": (
                    "YES_VISUAL_EVIDENCE_SUPPORTED_SELECTED_URL_FEATURE_GATE"
                ),
            },
            "steps": [
                {
                    "sequence_number": 1,
                    "decision_stage": "INPUT_INTERPRETATION",
                    "business_question": "What product is this?",
                    "evidence_considered": "main_text=Demo product",
                    "evidence_sources": ["submitted input"],
                    "visual_evidence_used": False,
                    "visual_evidence_details": "No visual evidence yet.",
                    "agent_judgement": "Demo Product Exact Variant",
                    "judgement_status": "RESOLVED",
                    "alternatives_considered": "Sibling variant",
                    "alternative_rejected": "Sibling variant",
                    "rejection_reason": "Exact identifier matched",
                    "business_rule_applied": "Resolve identity before search",
                    "effect_on_next_action": "Search manufacturer",
                    "confidence": "95%",
                    "final_outcome": "SEARCH_IDENTITY_ESTABLISHED",
                },
                {
                    "sequence_number": 2,
                    "decision_stage": "FINAL_SOURCE_SELECTION",
                    "business_question": "Which qualified source is primary?",
                    "evidence_considered": "manufacturer passed all gates",
                    "evidence_sources": ["source_selection.json"],
                    "visual_evidence_used": True,
                    "visual_evidence_details": "Package image confirmed feature",
                    "agent_judgement": "Use official manufacturer",
                    "judgement_status": "ACCEPTED",
                    "alternatives_considered": "Retailer",
                    "alternative_rejected": "Retailer",
                    "rejection_reason": "Lower source authority",
                    "business_rule_applied": "Manufacturer wins after strict gates",
                    "effect_on_next_action": "Deliver primary URL",
                    "confidence": "100%",
                    "final_outcome": "COMPLETED",
                },
            ],
        },
        "feature_assessments": [
            {
                "url": "https://manufacturer.example/demo",
                "source_role": "OFFICIAL_MANUFACTURER",
                "identity_accepted": True,
                "coverage": 1.0,
                "evidence": [
                    {
                        "feature_id": "brand",
                        "feature_name": "brand",
                        "value": "Demo",
                        "status": "LLM_FOUND",
                        "confidence": 0.98,
                        "extraction_method": "vision_llm",
                        "evidence_location": "visual_asset:1",
                        "evidence_text": "Demo brand visible on pack",
                    }
                ],
            }
        ],
    }
    (artifact / "orchestrated_result.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    (artifact / "product_belief.json").write_text(
        json.dumps(
            {
                "leading_hypothesis": {"canonical_name": "Demo Product Exact Variant"},
                "evidence_ledger": [{"evidence": "EAN confirmed"}],
                "snapshots": [{"stage": "initial"}, {"stage": "final"}],
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "url": "https://manufacturer.example/demo",
                "source_role": "OFFICIAL_MANUFACTURER",
                "validation_status": "VERIFIED",
                "identity_status": "EXACT",
                "strict_selected": True,
            }
        ]
    ).to_csv(artifact / "candidates.csv", index=False)
    (artifact / "business_judgement_review.md").write_text(
        "# Business judgment review", encoding="utf-8"
    )
    return artifact


def test_resolve_artifact_dir_accepts_any_file_inside_artifact(tmp_path: Path) -> None:
    artifact = _write_artifact(tmp_path)
    assert resolve_artifact_dir(artifact / "candidates.csv") == artifact


def test_build_diagnostics_reconstructs_decision_and_visual_evidence(tmp_path: Path) -> None:
    artifact = _write_artifact(tmp_path)
    diagnostics = build_artifact_diagnostics(artifact)

    assert diagnostics.overview_df.iloc[0]["primary_url_role"] == "OFFICIAL_MANUFACTURER"
    assert len(diagnostics.business_judgement_steps_df) == 2
    assert len(diagnostics.candidates_df) == 1
    assert diagnostics.feature_evidence_df.iloc[0]["extraction_method"] == "vision_llm"
    assert "business_judgement_review.md" in set(
        diagnostics.artifact_inventory_df["file_name"]
    )


def test_diagnostic_plots_and_markdown_report_are_generated(tmp_path: Path) -> None:
    artifact = _write_artifact(tmp_path)
    diagnostics = build_artifact_diagnostics(artifact)

    mindmap = plot_artifact_mindmap(diagnostics)
    timeline = plot_business_judgement_timeline(diagnostics)
    assert mindmap.axes
    assert timeline.axes
    plt.close(mindmap)
    plt.close(timeline)

    report = write_artifact_diagnostic_report(diagnostics)
    text = report.read_text(encoding="utf-8")
    assert "Decision mindmap" in text
    assert "flowchart TD" in text
    assert "Chronological business judgments" in text
    assert "does not expose hidden chain-of-thought" in text
