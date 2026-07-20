from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.product_evidence_harness import batch_notebook_runtime as batch


def test_normalize_batch_input_accepts_business_column_aliases_and_preserves_ean() -> None:
    frame = pd.DataFrame(
        [
            {
                "MAIN TEXT": "Product A",
                "EAN": "0012345678905",
                "Retailer Name": "Retailer",
                "Country Code": "ch",
            },
            {
                "MAIN TEXT": "Product B",
                "EAN": "",
                "Retailer Name": "",
                "Country Code": "DE",
            },
        ]
    )

    normalized = batch.normalize_batch_input(frame)

    assert list(normalized["row_id"]) == ["BATCH-000001", "BATCH-000002"]
    assert normalized.loc[0, "ean"] == "0012345678905"
    assert normalized.loc[0, "country_code"] == "CH"
    assert normalized.loc[1, "country_code"] == "DE"


def test_normalize_batch_input_rejects_duplicate_row_ids() -> None:
    frame = pd.DataFrame(
        [
            {"row_id": "A", "main_text": "Product A", "country_code": "CH"},
            {"row_id": "A", "main_text": "Product B", "country_code": "DE"},
        ]
    )

    with pytest.raises(ValueError, match="row_id must be unique"):
        batch.normalize_batch_input(frame)


def test_recommended_parallelism_is_bounded_by_agent_and_browser(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_WORKERS", "6")
    monkeypatch.setenv("BROWSER_MAX_CONTEXTS", "3")
    assert batch.recommended_batch_parallelism() == 3


def test_batch_run_isolates_row_failure_and_writes_consolidated_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = pd.DataFrame(
        [
            {"row_id": "A", "main_text": "Product A", "country_code": "CH"},
            {"row_id": "B", "main_text": "Product B", "country_code": "DE"},
            {"row_id": "C", "main_text": "Product C", "country_code": "FR"},
        ]
    )

    monkeypatch.setattr(batch, "check_health", lambda: {"status": "healthy"})
    monkeypatch.setattr(
        batch,
        "submit_product",
        lambda product, feature_set: (
            (_ for _ in ()).throw(RuntimeError("synthetic failure"))
            if product["row_id"] == "B"
            else f"job-{product['row_id']}"
        ),
    )
    monkeypatch.setattr(batch, "_wait_for_job_quiet", lambda job_id: {"status": "COMPLETED"})
    monkeypatch.setattr(batch, "validate_result_contract", lambda result: result)
    monkeypatch.setattr(
        batch,
        "host_artifact_dir",
        lambda root, result: root / "data" / "artifacts" / result["product"]["row_id"],
    )

    def fake_api(method: str, path: str, payload=None, timeout: int = 30):
        row_id = path.split("/")[-2].removeprefix("job-")
        return {
            "job_status": "COMPLETED",
            "product": {"row_id": row_id},
            "primary_url": f"https://manufacturer.example/{row_id}",
            "primary_url_role": "OFFICIAL_MANUFACTURER",
            "manufacturer_url": f"https://manufacturer.example/{row_id}",
            "retailer_url": None,
            "source_selection": {
                "selection_reason": "OFFICIAL_MANUFACTURER_PRIMARY_AFTER_STRICT_GATES",
                "selected_source_tier_name": "LOCAL_MANUFACTURER",
            },
            "url_delivery": {"delivered": True, "strictly_verified": True},
            "primary_url_acceptance": {"accepted": True},
            "search": {"serpapi_requests_used": 1},
            "candidate_investigations": [],
            "business_judgement_review": {
                "judgement_count": 5,
                "visual_evidence_summary": {
                    "image_influenced_final_decision": "NO_VISUAL_EVIDENCE_RECORDED"
                },
            },
        }

    monkeypatch.setattr(batch, "api_json", fake_api)

    report = batch.run_batch_products(
        frame,
        project_root=tmp_path,
        max_parallel=2,
        run_id="test-run",
        print_progress=False,
    )

    assert len(report.results_df) == 3
    assert set(report.results_df["job_status"]) == {"COMPLETED", "FAILED"}
    assert report.summary["failed_rows"] == 1
    assert report.summary["successful_or_review_rows"] == 2
    assert (report.output_dir / "batch_results.csv").is_file()
    assert (report.output_dir / "batch_failures.csv").is_file()
    assert (report.output_dir / "batch_artifact_index.csv").is_file()
    summary = json.loads((report.output_dir / "batch_run_summary.json").read_text())
    assert summary["input_rows"] == 3
