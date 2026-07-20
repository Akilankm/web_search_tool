from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.product_evidence_harness.artifact_diagnostics import ArtifactDiagnostics
from src.product_evidence_harness.interactive_artifact_diagnostics import (
    build_interactive_artifact_dashboard,
)


def _diagnostics(tmp_path: Path) -> ArtifactDiagnostics:
    return ArtifactDiagnostics(
        artifact_dir=tmp_path,
        result={
            "primary_url": "https://manufacturer.example/product-1",
            "primary_url_role": "manufacturer",
        },
        overview_df=pd.DataFrame(
            [
                {
                    "job_status": "COMPLETED",
                    "primary_url_role": "manufacturer",
                    "primary_url": "https://manufacturer.example/product-1",
                    "identified_product": "Example Product",
                    "candidate_rows": 3,
                    "business_judgement_count": 2,
                    "feature_evidence_rows": 3,
                    "image_influenced_final_decision": "YES",
                    "selection_reason": "Manufacturer passed every strict gate",
                }
            ]
        ),
        product_input_df=pd.DataFrame(),
        business_judgement_steps_df=pd.DataFrame(
            [
                {
                    "sequence_number": 1,
                    "decision_stage": "IDENTIFY_PRODUCT",
                    "business_question": "Which exact product is represented?",
                    "evidence_considered": "EAN and submitted main text",
                    "evidence_sources": "input",
                    "agent_judgement": "Exact product identified",
                    "judgement_status": "accepted",
                    "business_rule_applied": "Exact identity precedes URL authority",
                    "effect_on_next_action": "Search official manufacturer",
                    "confidence": 0.91,
                },
                {
                    "sequence_number": 2,
                    "decision_stage": "SELECT_PRIMARY_URL",
                    "business_question": "Which qualified URL should be primary?",
                    "evidence_considered": "Identity, features, browser and images",
                    "evidence_sources": "manufacturer and retailer pages",
                    "visual_evidence_used": True,
                    "visual_evidence_details": "Packaging image confirmed pack form",
                    "agent_judgement": "Manufacturer is primary",
                    "judgement_status": "accepted",
                    "alternative_rejected": "Retailer page",
                    "rejection_reason": "Qualified but lower authority",
                    "business_rule_applied": "Authority is applied after strict gates",
                    "effect_on_next_action": "Deliver manufacturer URL",
                    "confidence": 0.96,
                    "final_outcome": "COMPLETED",
                },
            ]
        ),
        visual_evidence_summary_df=pd.DataFrame(),
        search_steps_df=pd.DataFrame(
            [
                {"name": "manufacturer_primary"},
                {"name": "country_alternative"},
                {"name": "global_fallback"},
            ]
        ),
        candidates_df=pd.DataFrame(
            [
                {
                    "url": "https://manufacturer.example/product-1",
                    "source_role": "manufacturer",
                    "coverage": 1.0,
                    "confidence": 0.96,
                    "strict_selected": True,
                    "identity_accepted": True,
                    "browser_openable": True,
                    "scrapable": True,
                    "evidence_count": 4,
                },
                {
                    "url": "https://retailer.example/product-1",
                    "source_role": "retailer",
                    "coverage": 0.82,
                    "confidence": 0.84,
                    "identity_accepted": True,
                    "browser_openable": True,
                    "scrapable": True,
                    "decision_reasons": "Exact local retailer alternative",
                    "evidence_count": 3,
                },
                {
                    "url": "https://marketplace.example/product-2",
                    "source_role": "marketplace",
                    "coverage": 0.2,
                    "confidence": 0.31,
                    "rejection_reasons": "Wrong variant",
                    "missing_features": "pack size",
                },
            ]
        ),
        feature_evidence_df=pd.DataFrame(
            [
                {
                    "url": "https://manufacturer.example/product-1",
                    "source_role": "manufacturer",
                    "feature_name": "Brand",
                    "value": "Example",
                    "status": "resolved",
                    "confidence": 0.99,
                    "extraction_method": "text",
                    "evidence_text": "Brand Example",
                },
                {
                    "url": "https://manufacturer.example/product-1",
                    "source_role": "manufacturer",
                    "feature_name": "Pack form",
                    "value": "Single",
                    "status": "resolved",
                    "confidence": 0.91,
                    "extraction_method": "vision_llm",
                    "evidence_text": "Front packaging shows one unit",
                },
                {
                    "url": "https://retailer.example/product-1",
                    "source_role": "retailer",
                    "feature_name": "Brand",
                    "value": "Example",
                    "status": "resolved",
                    "confidence": 0.84,
                    "extraction_method": "text",
                    "evidence_text": "Example product",
                },
            ]
        ),
        evidence_ledger_df=pd.DataFrame(),
        belief_updates_df=pd.DataFrame(),
        artifact_inventory_df=pd.DataFrame(
            [
                {
                    "file_name": "orchestrated_result.json",
                    "suffix": ".json",
                    "size_bytes": 1200,
                    "purpose": "Canonical machine-readable result",
                    "present_in_contract": True,
                    "path": str(tmp_path / "orchestrated_result.json"),
                },
                {
                    "file_name": "business_judgement_review.md",
                    "suffix": ".md",
                    "size_bytes": 800,
                    "purpose": "Human-comparable observable decision sequence",
                    "present_in_contract": True,
                    "path": str(tmp_path / "business_judgement_review.md"),
                },
            ]
        ),
        mindmap_nodes_df=pd.DataFrame(
            [
                {
                    "node_id": "root",
                    "label": "Product URL decision\nExample Product",
                    "group": "root",
                    "depth": 0,
                    "order": 0,
                },
                {
                    "node_id": "input",
                    "label": "Input\nExample Product",
                    "group": "input",
                    "depth": 1,
                    "order": 0,
                },
                {
                    "node_id": "search",
                    "label": "Search route\nmanufacturer → local → global",
                    "group": "search",
                    "depth": 1,
                    "order": 1,
                },
                {
                    "node_id": "judgments",
                    "label": "Observable business judgments",
                    "group": "judgments",
                    "depth": 1,
                    "order": 2,
                },
                {
                    "node_id": "judgment_1",
                    "label": "1. Identify product",
                    "group": "judgment_step",
                    "depth": 2,
                    "order": 1,
                },
            ]
        ),
        mindmap_edges_df=pd.DataFrame(
            [
                {"source": "root", "target": "input"},
                {"source": "root", "target": "search"},
                {"source": "root", "target": "judgments"},
                {"source": "judgments", "target": "judgment_1"},
            ]
        ),
    )


def test_interactive_dashboard_is_self_contained_and_table_free(tmp_path: Path) -> None:
    dashboard = build_interactive_artifact_dashboard(_diagnostics(tmp_path))

    assert dashboard.output_path == tmp_path / "artifact_diagnostics_interactive.html"
    assert dashboard.output_path.is_file()
    assert list(dashboard.figures) == [
        "Decision map",
        "Judgment timeline",
        "Candidate explorer",
        "Evidence explorer",
        "Artifact map",
    ]

    html = dashboard.output_path.read_text(encoding="utf-8")
    assert "openDiagTab" in html
    assert "Decision map" in html
    assert "Judgment timeline" in html
    assert "Candidate URL explorer" in html
    assert "Interactive evidence explorer" in html
    assert "Generated artifact map" in html
    assert '<script src="https://cdn.plot.ly' not in html
    assert "<table" not in html.lower()

    candidate_figure = dashboard.figures["Candidate explorer"]
    assert candidate_figure.layout.updatemenus
    assert len(candidate_figure.data) >= 3
    assert dashboard.figures["Evidence explorer"].data[0].type == "sunburst"
    assert dashboard.figures["Artifact map"].data[0].type == "treemap"


def test_diagnostics_notebook_uses_one_interactive_workspace() -> None:
    notebook = json.loads(
        Path("notebooks/03_artifact_diagnostics.ipynb").read_text(encoding="utf-8")
    )
    text = "\n".join(
        "".join(cell.get("source", []))
        if isinstance(cell.get("source"), list)
        else str(cell.get("source", ""))
        for cell in notebook["cells"]
    )

    assert "build_interactive_artifact_dashboard" in text
    assert "display_interactive_artifact_dashboard" in text
    assert "artifact_diagnostics_interactive.html" in text
    assert "matplotlib" not in text
    assert "seaborn" not in text
    assert "plot_artifact_mindmap" not in text
    assert "plot_business_judgement_timeline" not in text
    assert "display(diagnostics." not in text


def test_interactive_dependencies_remain_outside_lean_agent() -> None:
    agent_requirements = Path("requirements/agent.txt").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    compatibility = Path(
        "src/product_evidence_harness/compat_patches.py"
    ).read_text(encoding="utf-8")

    assert "plotly" in pyproject
    assert "ipywidgets" in pyproject
    assert "plotly" not in agent_requirements
    assert "ipywidgets" not in agent_requirements
    assert "interactive_artifact_diagnostics" not in compatibility


def test_interactive_diagnostics_documentation_contract() -> None:
    document = Path("docs/INTERACTIVE_ARTIFACT_DIAGNOSTICS.md").read_text(
        encoding="utf-8"
    )
    for required in (
        "Decision Map",
        "Judgment Timeline",
        "Candidates",
        "Evidence",
        "Artifacts",
        "artifact_diagnostics_interactive.html",
        "does not expose or reconstruct hidden chain-of-thought",
    ):
        assert required in document
