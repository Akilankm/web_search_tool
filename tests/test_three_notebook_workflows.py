from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_NAMES = (
    "01_single_product.ipynb",
    "02_batch_products.ipynb",
    "03_artifact_diagnostics.ipynb",
)


def _source(name: str) -> str:
    notebook = json.loads((ROOT / "notebooks" / name).read_text(encoding="utf-8"))
    return "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])


def test_exactly_three_supported_notebooks_exist_and_are_clean() -> None:
    actual = tuple(sorted(path.name for path in (ROOT / "notebooks").glob("*.ipynb")))
    assert actual == NOTEBOOK_NAMES

    for name in NOTEBOOK_NAMES:
        notebook = json.loads((ROOT / "notebooks" / name).read_text(encoding="utf-8"))
        assert notebook["nbformat"] == 4
        assert notebook["cells"]
        for cell in notebook["cells"]:
            if cell.get("cell_type") == "code":
                assert cell.get("execution_count") is None
                assert cell.get("outputs") == []
                compile(
                    "".join(cell.get("source", [])),
                    f"{name}:code-cell",
                    "exec",
                )


def test_single_product_notebook_is_judgment_first_and_complete() -> None:
    source = _source("01_single_product.ipynb")
    for token in (
        "RUN_SINGLE_PRODUCT = False",
        "run_product(product, FEATURE_SET)",
        "build_artifact_diagnostics",
        "business_judgement_steps_df",
        "visual_evidence_summary_df",
        "primary_url",
        "manufacturer_url",
        "retailer_url",
        "single_product_diagnostics.xlsx",
        "SHARE WITH HUMAN CODER",
    ):
        assert token in source


def test_batch_notebook_validates_csv_and_runs_bounded_parallel_products() -> None:
    source = _source("02_batch_products.ipynb")
    for token in (
        "CSV_PATH",
        "MAX_PARALLEL_PRODUCTS",
        "normalize_batch_input",
        "run_batch_products",
        "batch_results.csv",
        "batch_failures.csv",
        "batch_artifact_index.csv",
        "throughput",
        "business_judgement_review_path",
    ):
        assert token in source


def test_artifact_notebook_is_offline_and_interactively_complete() -> None:
    source = _source("03_artifact_diagnostics.ipynb")
    for token in (
        "ARTIFACT_PATH",
        "build_artifact_diagnostics",
        "build_interactive_artifact_dashboard",
        "display_interactive_artifact_dashboard",
        "artifact_diagnostics_interactive.html",
        "Decision Map",
        "Judgment Timeline",
        "Candidates",
        "Evidence",
        "Artifacts",
        "artifact_diagnostic_report.md",
        "artifact_diagnostic_workbook.xlsx",
        "business_judgement_review.md",
        "not hidden chain-of-thought",
    ):
        assert token in source
    assert "ensure_platform_ready" not in source
    assert "run_product" not in source
    assert "plot_artifact_mindmap" not in source
    assert "plot_business_judgement_timeline" not in source
    assert "display(diagnostics." not in source
