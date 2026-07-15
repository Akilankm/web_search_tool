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

    assert "result.get('job_status')" in source
    assert "(result.get('product') or {}).get('row_id')" in source
    assert "feature_evidence_df" in source
    assert "result.get('primary_url_acceptance')" in source
    assert "result.get('url_delivery')" in source
    assert "result.get('search')" in source
    assert "build_single_product_diagnostics" in source
    assert "build_adaptive_search_diagnostics" in source
    assert "result.get('row_id')" not in source
    assert "result.get('feature_evidence')" not in source


def test_notebook_forces_repository_local_package_and_evicts_stale_modules() -> None:
    source = notebook_source()

    assert "LOCAL_PACKAGE" in source
    assert "notebook_runtime.py" in source
    assert "sys.modules" in source
    assert "del sys.modules[module_name]" in source
    assert "Wrong package loaded" in source
    assert "LOCAL_PACKAGE not in loaded_package.parents" in source


def test_notebook_defaults_to_committed_toy_feature_schema() -> None:
    source = notebook_source()
    runtime = runtime_source()

    assert 'DEFAULT_FEATURE_SET = "toy_features"' in runtime
    assert "FEATURE_SET = 'toy_features'" in source
    assert "inputs/private/toy_features.json" in source
    assert "DEFAULT_FEATURE_SET not in feature_sets" in source
    assert "feature_set: str = DEFAULT_FEATURE_SET" in runtime


def test_notebook_builds_complete_single_product_eda_tables() -> None:
    source = notebook_source()

    for name in (
        "url_delivery_df",
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
        "source_hierarchy_df",
        "source_tier_summary_df",
    ):
        assert name in source

    assert "Mandatory product URL delivery" in source
    assert "Source hierarchy by SerpAPI credit" in source
    assert "Final URL selection RCA" in source
    assert "Search-engine yield and conversion" in source
    assert "One canonical product URL candidate per row" in source


def test_notebook_exposes_mandatory_url_contract() -> None:
    source = notebook_source()

    for field in (
        "primary_url",
        "url_delivery_status",
        "strictly_verified",
        "strict_primary_accepted",
        "delivered",
        "mandatory_url_delivery.json",
    ):
        assert field in source

    assert "Mandatory URL contract violated" in source
    assert "if not result.get('primary_url') or not delivery.get('delivered')" in source
    assert "REVIEW_REQUIRED" in source
    assert "MANDATORY_PRODUCT_URL_NOT_FOUND" in source


def test_notebook_exposes_adaptive_search_contract() -> None:
    source = notebook_source()
    runtime = runtime_source()

    for field in (
        "engine_sequence",
        "target_source_tiers",
        "serpapi_requests_used",
        "search_stop_reason",
        "planner_source",
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
    for call in (
        "plot_engine_credit_allocation(adaptive_diagnostics)",
        "plot_engine_candidate_yield(adaptive_diagnostics)",
        "plot_credit_progression(adaptive_diagnostics)",
        "plot_funnel(diagnostics)",
        "plot_stage_yield(diagnostics)",
        "plot_candidate_outcomes(diagnostics)",
        "plot_confidence_distribution(diagnostics)",
        "plot_confidence_vs_coverage(diagnostics)",
        "plot_domain_quality(diagnostics)",
        "plot_rejection_reasons(diagnostics)",
        "plot_feature_heatmap(diagnostics)",
    ):
        assert call in source


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
    assert "mandatory_url_delivery.json" in source
    assert "source_tier_summary" in source
    assert "url_delivery" in source


def test_notebook_docs_match_mandatory_url_contract() -> None:
    notebook_doc = (ROOT / "docs" / "NOTEBOOK_USAGE.md").read_text(encoding="utf-8")
    mandatory_doc = (ROOT / "docs" / "MANDATORY_PRODUCT_URL.md").read_text(encoding="utf-8")
    adaptive_doc = (ROOT / "docs" / "ADAPTIVE_SERPAPI_SEARCH.md").read_text(encoding="utf-8")
    hierarchy_doc = (ROOT / "docs" / "SOURCE_AUTHORITY_HIERARCHY.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for text in (notebook_doc, mandatory_doc, adaptive_doc, hierarchy_doc, readme):
        assert "product" in text.lower()
        assert "url" in text.lower()

    assert "url_delivery_df" in notebook_doc
    assert "MANDATORY_PRODUCT_URL_NOT_FOUND" in notebook_doc
    assert "empty product URL" in mandatory_doc
    assert "Amazon/eBay" in hierarchy_doc
    assert "search_actions_df" in adaptive_doc
