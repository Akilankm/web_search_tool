from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.product_evidence_harness import batch_notebook_runtime as batch
from src.product_evidence_harness.structured_no_url_outcome import (
    NO_URL_DELIVERY_STATUS,
    NO_URL_OUTCOME_CODE,
)


def test_batch_keeps_structured_no_url_row_out_of_failure_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    frame = pd.DataFrame(
        [{"row_id": "NO-URL-1", "main_text": "Obscure product", "country_code": "GB"}]
    )

    artifact_dir = tmp_path / "data" / "artifacts" / "NO-URL-1"
    artifact_dir.mkdir(parents=True)
    review_path = artifact_dir / "business_judgement_review.md"
    review_path.write_text("# Review\n", encoding="utf-8")

    result = {
        "job_status": "REVIEW_REQUIRED",
        "product": {"row_id": "NO-URL-1"},
        "primary_url": None,
        "primary_url_role": "NONE",
        "manufacturer_url": None,
        "retailer_url": None,
        "source_selection": {
            "selection_reason": NO_URL_DELIVERY_STATUS,
            "source_tier_name": "NONE",
        },
        "url_delivery": {
            "delivered": False,
            "strictly_verified": False,
            "status": NO_URL_DELIVERY_STATUS,
        },
        "primary_url_acceptance": {"accepted": False},
        "search": {"serpapi_requests_used": 3},
        "candidate_investigations": [],
        "business_judgement_review": {
            "artifact_path": str(review_path),
            "judgement_count": 7,
            "visual_evidence_summary": {
                "image_influenced_final_decision": "NO_VISUAL_EVIDENCE_RECORDED"
            },
        },
        "resolution_outcome": {
            "code": NO_URL_OUTCOME_CODE,
            "message": "No safe direct product URL was found within the bounded search policy.",
        },
    }

    monkeypatch.setattr(batch, "check_health", lambda: {"status": "healthy"})
    monkeypatch.setattr(batch, "submit_product", lambda product, feature_set: "job-no-url")
    monkeypatch.setattr(
        batch,
        "_wait_for_job_quiet",
        lambda job_id: {"status": "REVIEW_REQUIRED"},
    )
    monkeypatch.setattr(batch, "validate_result_contract", lambda payload: payload)
    monkeypatch.setattr(batch, "api_json", lambda *args, **kwargs: result)
    monkeypatch.setattr(batch, "host_artifact_dir", lambda root, payload: artifact_dir)

    report = batch.run_batch_products(
        frame,
        project_root=tmp_path,
        max_parallel=1,
        run_id="no-url-batch",
        print_progress=False,
    )

    assert report.results_df.loc[0, "job_status"] == "REVIEW_REQUIRED"
    assert report.results_df.loc[0, "primary_url_role"] == "NONE"
    assert report.results_df.loc[0, "url_delivered"] == False  # noqa: E712
    assert report.failures_df.empty
    assert report.summary["successful_or_review_rows"] == 1
    assert report.summary["failed_rows"] == 0
    assert (report.output_dir / "batch_results.csv").is_file()
    failure_csv = pd.read_csv(report.output_dir / "batch_failures.csv")
    assert failure_csv.empty
