from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException

from src.product_evidence_harness.agent_service.jobs import InMemoryJobStore, JobStatus
from src.product_evidence_harness.agent_service.orchestrator import ProductEvidenceOrchestrator


app = FastAPI(title="Product Evidence Agent", version="0.5.0")
store = InMemoryJobStore()
executor = ThreadPoolExecutor(max_workers=max(1, int(os.getenv("AGENT_WORKERS", "2"))))
orchestrator = ProductEvidenceOrchestrator()


@app.get("/health")
def health() -> dict:
    return orchestrator.health()


@app.post("/v1/jobs", status_code=202)
def create_job(payload: dict) -> dict:
    requested_id = str(payload.get("row_id") or payload.get("product", {}).get("row_id") or "job")
    record = store.create(payload, requested_id=requested_id)
    executor.submit(_run_job, record.job_id)
    return {"job_id": record.job_id, "status": record.status.value}


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    try:
        return store.get(job_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@app.get("/v1/jobs/{job_id}/result")
def get_result(job_id: str) -> dict:
    try:
        record = store.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    if record.status not in {JobStatus.COMPLETED, JobStatus.REVIEW_REQUIRED}:
        raise HTTPException(status_code=409, detail=f"Job is not complete: {record.status.value}")
    return record.result or {}


def _run_job(job_id: str) -> None:
    record = store.get(job_id)
    store.update(job_id, status=JobStatus.RUNNING, stage="VALIDATING_INPUT")

    def progress(stage: str, message: str) -> None:
        store.update(job_id, status=JobStatus.RUNNING, stage=stage, message=message)

    try:
        result = orchestrator.run(record.payload, progress=progress)
        final_status = JobStatus.COMPLETED if result.get("coding_ready") else JobStatus.REVIEW_REQUIRED
        store.update(
            job_id,
            status=final_status,
            stage=final_status.value,
            message="Product evidence workflow completed",
            result=result,
        )
    except Exception as exc:
        store.update(
            job_id,
            status=JobStatus.FAILED,
            stage="FAILED",
            message="Product evidence workflow failed",
            error=f"{type(exc).__name__}: {exc}",
        )
