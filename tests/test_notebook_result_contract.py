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
    assert 'result.get("primary_url_acceptance")' in source
    assert 'result.get("search")' in source
    assert 'result.get("agentic_browser")' in source
    assert 'result.get("candidate_investigations")' in source
    assert "summarize_result(result)" in source

    assert 'result.get("row_id")' not in source
    assert 'result.get("feature_evidence")' not in source


def test_notebook_exposes_agentic_and_strict_acceptance_fields() -> None:
    source = notebook_source()

    assert 'search.get("serpapi_requests_used")' in source
    assert 'search.get("stages")' in source
    assert 'agentic.get("candidate_urls_admitted")' in source
    assert 'agentic.get("candidate_investigations_completed")' in source
    assert 'product_match.get("selection_scope")' in source
    assert 'acceptance.get("accepted")' in source
    assert 'acceptance.get("reasons")' in source
    assert "strict_primary_url_accepted" in source
    assert "three_stage_contract_enforced" in source
    assert "agentic_browser_contract_enforced" in source
    assert "agentic_tools" in source
    assert "serpapi_request_limit" in source


def test_notebook_suppresses_duplicate_progress_and_prints_heartbeat() -> None:
    source = notebook_source()

    assert "HEARTBEAT_SECONDS = 30" in source
    assert "last_signature" in source
    assert "signature != last_signature" in source
    assert "still running" in source
    assert "AGENTIC_BROWSER_INVESTIGATION" in source or "LLM-controlled browser" in source


def test_notebook_uses_repository_local_artifact_paths() -> None:
    source = notebook_source()

    assert 'PROJECT_ROOT / "data" / "artifacts"' in source
    assert 'PROJECT_ROOT / "data" / "artifacts" / "notebook_batch_summary.csv"' in source
    assert 'Path("artifacts/notebook_batch_summary.csv")' not in source
    assert "host_artifact_dir(result)" in source
    assert "primary_url_acceptance" in source
    assert "CAND-*/agentic/investigation.json" in source


def test_notebook_documents_terminal_status_semantics() -> None:
    source = notebook_source()

    assert "REVIEW_REQUIRED" in source
    assert "successful terminal workflow states" in source
    assert "Only `FAILED` represents an execution failure" in source


def test_notebook_docs_match_agentic_result_contract() -> None:
    notebook_doc = (ROOT / "docs" / "NOTEBOOK_USAGE.md").read_text(encoding="utf-8")
    operations_doc = (ROOT / "docs" / "AZUREML_OPERATIONS.md").read_text(encoding="utf-8")
    agentic_doc = (ROOT / "docs" / "AGENTIC_BROWSER.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for text in (notebook_doc, operations_doc, agentic_doc, readme):
        assert "agentic" in text.lower()
        assert "primary_url" in text
        assert "three" in text.lower()
        assert "global" in text.lower()
        assert "deterministic" in text.lower()

    assert "candidate_investigations" in notebook_doc
    assert "data/artifacts/notebook_batch_summary.csv" in notebook_doc
    assert "docs/NOTEBOOK_USAGE.md" in readme
    assert "docs/AGENTIC_BROWSER.md" in readme
