from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SINGLE = ROOT / "notebooks" / "01_single_product.ipynb"
BATCH = ROOT / "notebooks" / "02_batch_products.ipynb"
DIAGNOSTICS = ROOT / "notebooks" / "03_artifact_diagnostics.ipynb"


def notebook_source(path: Path) -> str:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
    )


def runtime_source() -> str:
    return (ROOT / "src" / "product_evidence_harness" / "notebook_runtime.py").read_text(
        encoding="utf-8"
    )


def test_single_notebook_uses_current_result_and_judgment_contract() -> None:
    source = notebook_source(SINGLE)
    for token in (
        "ensure_platform_ready",
        "manufacturer_first_primary_url",
        "business_judgement_review_artifact",
        "run_product(product, FEATURE_SET)",
        "host_artifact_dir(PROJECT_ROOT, result)",
        "build_artifact_diagnostics",
        "primary_url",
        "primary_url_role",
        "manufacturer_url",
        "retailer_url",
        "source_selection",
        "business_judgement_steps_df",
        "visual_evidence_summary_df",
        "single_product_diagnostics.xlsx",
    ):
        assert token in source


def test_batch_notebook_uses_current_parallel_and_artifact_contract() -> None:
    source = notebook_source(BATCH)
    for token in (
        "ensure_platform_ready",
        "load_batch_csv",
        "normalize_batch_input",
        "recommended_batch_parallelism",
        "run_batch_products",
        "MAX_PARALLEL_PRODUCTS",
        "batch_results.csv",
        "batch_failures.csv",
        "batch_artifact_index.csv",
        "batch_run_summary.json",
        "business_judgement_review_path",
        "throughput_products_per_minute",
    ):
        assert token in source


def test_artifact_diagnostics_notebook_is_offline_and_complete() -> None:
    source = notebook_source(DIAGNOSTICS)
    for token in (
        "ARTIFACT_PATH",
        "build_artifact_diagnostics",
        "plot_artifact_mindmap",
        "plot_business_judgement_timeline",
        "write_artifact_diagnostic_report",
        "artifact_diagnostic_workbook.xlsx",
        "business_judgement_review.md",
        "first divergent step",
    ):
        assert token in source
    assert "ensure_platform_ready" not in source
    assert "run_product" not in source


def test_notebook_runtime_retains_self_healing_and_mandatory_url_contract() -> None:
    runtime = runtime_source()
    for token in (
        "RUNTIME_CONTRACT_VERSION",
        "recover_platform",
        "subprocess.Popen",
        "--clean-build",
        "PRODUCT_HARNESS_NOTEBOOK_AUTO_RECOVER_PLATFORM",
        "PRODUCT_HARNESS_NOTEBOOK_CLEAN_BUILD_ON_RECOVERY",
        "validate_result_contract",
        "MANDATORY_PRODUCT_URL_NOT_DELIVERED",
        "HEARTBEAT_SECONDS = 30",
        "still running",
    ):
        assert token in runtime


def test_notebook_docs_describe_all_three_workflows() -> None:
    documentation = {
        "readme": (ROOT / "README.md").read_text(encoding="utf-8"),
        "notebooks": (ROOT / "docs" / "NOTEBOOK_USAGE.md").read_text(encoding="utf-8"),
        "azureml": (ROOT / "docs" / "AZUREML_OPERATIONS.md").read_text(encoding="utf-8"),
        "final": (ROOT / "docs" / "FINAL_SYSTEM_CONTRACT.md").read_text(encoding="utf-8"),
        "management": (ROOT / "docs" / "MANAGEMENT_DEMO_GUIDE.md").read_text(encoding="utf-8"),
    }
    for text in documentation.values():
        assert "01_single_product.ipynb" in text
        assert "02_batch_products.ipynb" in text
        assert "03_artifact_diagnostics.ipynb" in text
        assert "manufacturer" in text.lower()
        assert "business" in text.lower()

    notebook_doc = documentation["notebooks"]
    for token in (
        "batch_results.csv",
        "batch_run_summary.json",
        "artifact_diagnostic_report.md",
        "artifact_diagnostic_workbook.xlsx",
        "bounded parallel",
        "observable",
    ):
        assert token in notebook_doc
