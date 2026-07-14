from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = ROOT / "notebooks" / "01_run_product_evidence.ipynb"


def notebook_source() -> str:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
    )


def runtime_source() -> str:
    return (ROOT / "src" / "product_evidence_harness" / "notebook_runtime.py").read_text(
        encoding="utf-8"
    )


def test_notebook_uses_current_orchestrated_result_schema() -> None:
    source = notebook_source()

    assert 'result.get("job_status")' in source
    assert '(result.get("product") or {}).get("row_id")' in source
    assert "feature_evidence_df" in source
    assert 'result.get("primary_url_acceptance")' in source
    assert 'result.get("search")' in source
    assert "build_single_product_diagnostics" in source
    assert "build_adaptive_search_diagnostics" in source
    assert 'result.get("row_id")' not in source
    assert 'result.get("feature_evidence")' not in source


def test_notebook_defaults_to_committed_toy_feature_schema() -> None:
    source = notebook_source()
    runtime = runtime_source()

    assert 'DEFAULT_FEATURE_SET = "toy_features"' in runtime
    assert 'FEATURE_SET = "toy_features"' in source
    assert "inputs/private/toy_features.json" in source
    assert "DEFAULT_FEATURE_SET not in feature_sets" in source
    assert "feature_set: str = DEFAULT_FEATURE_SET" in runtime


def test_notebook_builds_complete_single_product_eda_tables() -> None:
    source = notebook_source()

    for name in (
        "results_df",
        "search_stages_df",
        "serp_results_df",
        "funnel_df",
        "domain_summary_df",
        "stage_quality_df",
        "agentic_df",
        "feature_evidence_df",
        "feature_matrix_df",
        "rejection_reasons_df",
        "selection_rca_df",
        "search_actions_df",
        "search_engine_summary_df",
        "search_handles_df",
        "search_decision_rca_df",
    ):
        assert name in source

    assert "Candidate-level acceptance and selection" in source
    assert "Final URL selection RCA" in source
    assert "SERP stage quality ratios" in source
    assert "Domain-level candidate quality" in source
    assert "Most frequent rejection and blocking reasons" in source
    assert "Adaptive SerpAPI credit decisions" in source
    assert "Search-engine yield and conversion" in source


def test_notebook_exposes_candidate_acceptance_funnel() -> None:
    source = notebook_source()
    for field in (
        "scrape_attempted",
        "technical_scrapable",
        "scrape_success",
        "content_utility_score",
        "agentic_investigated",
        "browser_openable",
        "identity_accepted",
        "coverage",
        "feature_complete",
        "quality_verified",
        "strict_selected",
        "review_selected",
        "final_candidate_status",
    ):
        assert field in source


def test_notebook_exposes_adaptive_search_contract() -> None:
    source = notebook_source()
    runtime = runtime_source()

    for field in (
        "engine_sequence",
        "serpapi_requests_used",
        "search_stop_reason",
        "planner_source",
        "handles_discovered",
        "working_url_found",
    ):
        assert field in source
    assert "adaptive_search_contract_enforced" in runtime
    assert "llm_search_planning_enabled" in runtime
    assert "llm_search_feedback_enabled" in runtime
    assert "serpapi_request_limit" in runtime


def test_notebook_includes_graphical_diagnostics() -> None:
    source = notebook_source()

    assert "matplotlib" in source
    assert "seaborn" in source
    assert "rich" in source.lower()
    assert "plot_engine_credit_allocation(adaptive_diagnostics)" in source
    assert "plot_engine_candidate_yield(adaptive_diagnostics)" in source
    assert "plot_credit_progression(adaptive_diagnostics)" in source
    assert "plot_funnel(diagnostics)" in source
    assert "plot_stage_yield(diagnostics)" in source
    assert "plot_candidate_outcomes(diagnostics)" in source
    assert "plot_confidence_distribution(diagnostics)" in source
    assert "plot_confidence_vs_coverage(diagnostics)" in source
    assert "plot_domain_quality(diagnostics)" in source
    assert "plot_rejection_reasons(diagnostics)" in source
    assert "plot_feature_heatmap(diagnostics)" in source


def test_notebook_auto_installs_only_missing_eda_dependencies() -> None:
    source = notebook_source()

    assert "PACKAGE_IMPORTS" in source
    assert "missing_specs" in source
    assert "pip" in source
    assert "pandas>=2.2,<3" in source
    assert "matplotlib>=3.8,<4" in source
    assert "seaborn>=0.13.2,<1" in source
    assert "rich>=13.7,<15" in source
    assert "openpyxl>=3.1,<4" in source


def test_notebook_runtime_suppresses_duplicate_progress_and_prints_heartbeat() -> None:
    runtime = runtime_source()

    assert "HEARTBEAT_SECONDS = 30" in runtime
    assert "last_signature" in runtime
    assert "signature != last_signature" in runtime
    assert "still running" in runtime


def test_notebook_uses_repository_local_artifact_paths_and_exports_rca() -> None:
    source = notebook_source()
    runtime = runtime_source()
    diagnostics_source = (
        ROOT / "src" / "product_evidence_harness" / "notebook_diagnostics.py"
    ).read_text(encoding="utf-8")

    assert 'project_root / "data" / "artifacts"' in runtime
    assert "host_artifact_dir(PROJECT_ROOT, result)" in source
    assert "candidates.csv" in diagnostics_source
    assert "feature_evidence.csv" in diagnostics_source
    assert "single_product_diagnostics.xlsx" in source
    assert "diagnostics.tables()" in source
    assert "export_adaptive_search_tables" in source
    assert "adaptive_search_trace.json" in source


def test_notebook_documents_terminal_status_semantics() -> None:
    source = notebook_source()

    assert "REVIEW_REQUIRED" in source
    assert "successful terminal workflow states" in source
    assert "Only `FAILED` represents an execution failure" in source


def test_notebook_docs_match_diagnostic_contract() -> None:
    notebook_doc = (ROOT / "docs" / "NOTEBOOK_USAGE.md").read_text(encoding="utf-8")
    diagnostics_doc = (ROOT / "docs" / "SINGLE_PRODUCT_DIAGNOSTICS.md").read_text(encoding="utf-8")
    adaptive_doc = (ROOT / "docs" / "ADAPTIVE_SERPAPI_SEARCH.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for text in (notebook_doc, diagnostics_doc, adaptive_doc, readme):
        assert "results_df" in text
        assert "candidate" in text.lower()
        assert "primary_url" in text
        assert "three" in text.lower()
        assert "deterministic" in text.lower()

    assert "inputs/private/toy_features.json" in notebook_doc
    assert "single_product_diagnostics.xlsx" in diagnostics_doc
    assert "docs/SINGLE_PRODUCT_DIAGNOSTICS.md" in readme
    assert "search_actions_df" in adaptive_doc
