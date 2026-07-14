from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException

from src.product_evidence_harness.agent_service.jobs import InMemoryJobStore, JobStatus
from src.product_evidence_harness.progress_context import browser_progress_callback
from src.product_evidence_harness.agent_service.strict_orchestrator import (
    StrictProductEvidenceOrchestrator,
)
from src.product_evidence_harness.three_stage_environment import validate_runtime_environment
from src.product_evidence_harness.llm.service import LLMConfig


app = FastAPI(title="Product Evidence Agent", version="0.8.0")
store = InMemoryJobStore()
executor = ThreadPoolExecutor(max_workers=max(1, int(os.getenv("AGENT_WORKERS", "2"))))
orchestrator = StrictProductEvidenceOrchestrator()


def _enabled(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _validate_runtime() -> tuple[dict | None, str | None]:
    try:
        report = validate_runtime_environment(
            None,
            strict_file_permissions=False,
        )
        llm_required = (
            _enabled("PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER", True)
            or _enabled("PRODUCT_HARNESS_ENABLE_VISION_REASONING", True)
            or _enabled("PRODUCT_HARNESS_ENABLE_LLM_FEATURE_REASONING", False)
        )
        if llm_required:
            LLMConfig.from_env()
        return report.to_dict(), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


@app.get("/health")
def health() -> dict:
    configuration, configuration_error = _validate_runtime()
    service = orchestrator.health()
    if configuration_error:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "configuration_error": configuration_error,
                "browser_service": service.get("browser_service"),
            },
        )
    if service.get("status") != "healthy":
        raise HTTPException(status_code=503, detail=service)
    return {**service, "configuration": configuration}


@app.post("/v1/jobs", status_code=202)
def create_job(payload: dict) -> dict:
    _configuration, configuration_error = _validate_runtime()
    if configuration_error:
        raise HTTPException(status_code=503, detail=configuration_error)
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
        with browser_progress_callback(progress):
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
