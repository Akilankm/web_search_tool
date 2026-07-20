from __future__ import annotations

from pathlib import Path

from src.product_evidence_harness.agent_service import app as agent_app
from src.product_evidence_harness.agent_service.jobs import InMemoryJobStore, JobStatus
from src.product_evidence_harness.business_judgement_artifact import (
    write_business_judgement_review,
)
from src.product_evidence_harness.no_url_business_review import (
    augment_no_url_business_review,
)
from src.product_evidence_harness.notebook_runtime import validate_result_contract
from src.product_evidence_harness.structured_no_url_outcome import (
    NO_URL_OUTCOME_CODE,
    build_structured_no_url_outcome,
)


def _result(tmp_path: Path) -> dict:
    result = {
        "job_status": "REVIEW_REQUIRED",
        "artifact_dir": str(tmp_path),
        "product": {
            "row_id": "ROW-NO-URL",
            "main_text": "Obscure exact product",
            "country_code": "GB",
            "retailer_name": None,
            "ean": None,
            "language_code": "en",
        },
        "product_identification": {
            "resolution_status": "AMBIGUOUS",
            "leading_hypothesis": {"canonical_name": "Obscure exact product"},
        },
        "search": {
            "market_decision_path": [
                "manufacturer_primary",
                "country_alternative",
                "global_fallback",
            ],
            "serpapi_requests_used": 3,
            "serpapi_request_limit": 3,
            "stages": [
                {"name": "manufacturer_primary", "results_returned": 0},
                {"name": "country_alternative", "results_returned": 0},
                {"name": "global_fallback", "results_returned": 0},
            ],
        },
        "product_match": {},
        "primary_url_acceptance": {"accepted": False},
        "evidence_set": {},
        "feature_assessments": [],
        "browser_evidence": [],
        "candidate_investigations": [],
    }
    result = build_structured_no_url_outcome(result)
    write_business_judgement_review(result, tmp_path)
    augment_no_url_business_review(result, tmp_path)
    return result


def test_agent_job_preserves_no_url_result_as_review_required(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store = InMemoryJobStore()
    result = _result(tmp_path)

    monkeypatch.setattr(agent_app, "store", store)
    monkeypatch.setattr(agent_app.orchestrator, "run", lambda payload, progress=None: result)

    record = store.create(
        {
            "product": result["product"],
            "feature_set": "toy_features",
        },
        requested_id="ROW-NO-URL",
    )
    agent_app._run_job(record.job_id)

    finished = store.get(record.job_id)
    assert finished.status == JobStatus.REVIEW_REQUIRED
    assert finished.error is None
    assert finished.result is result
    assert finished.result["resolution_outcome"]["code"] == NO_URL_OUTCOME_CODE
    assert finished.result["url_delivery"]["delivered"] is False
    assert validate_result_contract(finished.result) is finished.result


def test_no_url_business_review_is_explicit_and_non_contradictory(tmp_path: Path) -> None:
    result = _result(tmp_path)
    markdown = (tmp_path / "business_judgement_review.md").read_text(encoding="utf-8")

    assert "CONTROLLED NO-URL REVIEW OUTCOME" in markdown
    assert NO_URL_OUTCOME_CODE in markdown
    assert "not an unhandled software exception" in markdown
    assert "no URL means explicit failure" not in markdown
    assert result["business_judgement_review"]["human_review_status"] == (
        "PENDING_NO_URL_RESOLUTION_REVIEW"
    )
    assert result["business_judgement_review"]["steps"][-1]["decision_stage"] == (
        "FINAL_NO_SAFE_URL_REVIEW_OUTCOME"
    )
