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


def test_notebook_uses_current_orchestrated_result_schema() -> None:
    source = notebook_source()

    assert 'result.get("job_status")' in source
    assert '(result.get("product") or {}).get("row_id")' in source
    assert 'result.get("feature_assessments")' in source
    assert 'result.get("browser_evidence")' in source
    assert "summarize_result(result)" in source

    assert 'result.get("row_id")' not in source
    assert 'result.get("feature_evidence")' not in source


def test_notebook_uses_repository_local_artifact_paths() -> None:
    source = notebook_source()

    assert 'PROJECT_ROOT / "data" / "artifacts"' in source
    assert 'PROJECT_ROOT / "data" / "artifacts" / "notebook_batch_summary.csv"' in source
    assert 'Path("artifacts/notebook_batch_summary.csv")' not in source
    assert "host_artifact_dir(result)" in source


def test_notebook_documents_terminal_status_semantics() -> None:
    source = notebook_source()

    assert "REVIEW_REQUIRED" in source
    assert "successful terminal workflow states" in source
    assert "Only `FAILED` represents an execution failure" in source


def test_notebook_docs_match_the_result_contract() -> None:
    notebook_doc = (ROOT / "docs" / "NOTEBOOK_USAGE.md").read_text(encoding="utf-8")
    operations_doc = (ROOT / "docs" / "AZUREML_OPERATIONS.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for text in (notebook_doc, operations_doc, readme):
        assert "product.row_id" in text
        assert "job_status" in text
        assert "feature_assessments" in text
        assert "data/artifacts/notebook_batch_summary.csv" in text

    assert "docs/NOTEBOOK_USAGE.md" in readme
