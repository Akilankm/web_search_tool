from src.product_evidence_harness.agent_service.jobs import InMemoryJobStore, JobStatus


def test_job_store_lifecycle() -> None:
    store = InMemoryJobStore()
    record = store.create({"row_id": "ROW-1"})
    assert record.status == JobStatus.QUEUED
    updated = store.update(record.job_id, status=JobStatus.RUNNING, stage="SEARCHING")
    assert updated.stage == "SEARCHING"
    finished = store.update(record.job_id, status=JobStatus.COMPLETED, result={"ok": True})
    assert finished.result == {"ok": True}
