from __future__ import annotations

from product_evidence_harness.feedback import ReviewFeedbackRecord, ReviewFeedbackStore, RetailerDomainMemory


def test_review_feedback_store_round_trips_and_summarizes(tmp_path) -> None:
    store = ReviewFeedbackStore(tmp_path / "feedback.jsonl")
    store.append(ReviewFeedbackRecord(
        row_id="row-1",
        review_status="ACCEPTED_WITH_CORRECTION",
        accepted_url="https://example.cz/product/1",
        rejected_url="https://bad.example/listing",
        correct_url="https://example.cz/product/1",
        review_reason="WRONG_VARIANT",
        failure_taxonomy_at_review=("VARIANT_CONFLICT",),
    ))

    records = store.read_all()
    summary = store.summarize()

    assert len(records) == 1
    assert summary["reviewed_count"] == 1
    assert summary["review_reason_counts"]["WRONG_VARIANT"] == 1
    assert summary["failure_taxonomy_counts"]["VARIANT_CONFLICT"] == 1


def test_retailer_domain_memory_records_preferences() -> None:
    memory = RetailerDomainMemory()
    memory.record(retailer_name="Example Retailer", country_code="CZ", domain="example.cz", outcome="exact_match")
    memory.record(retailer_name="Example Retailer", country_code="CZ", domain="example.cz", outcome="exact_match")
    memory.record(retailer_name="Example Retailer", country_code="CZ", domain="other.cz", outcome="thin_page")

    assert memory.preferred_domains(retailer_name="Example Retailer", country_code="CZ", limit=1) == ["example.cz"]
    assert memory.to_dict()["example retailer::CZ"]["outcomes"]["exact_match"] == 2
