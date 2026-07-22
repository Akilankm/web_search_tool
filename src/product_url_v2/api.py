from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from product_url_v2.browser import BrowserClient
from product_url_v2.config import RuntimeConfig, load_config
from product_url_v2.models import ProductInput, RunEvent, to_jsonable
from product_url_v2.orchestrator import ProductURLOrchestrator


class ProductPayload(BaseModel):
    row_id: str | None = None
    main_text: str = Field(min_length=1)
    country_code: str = Field(min_length=2, max_length=2)
    retailer_name: str | None = None
    ean: str | None = None
    language_code: str | None = None
    feature_set: str = "toy"
    runtime_options: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class Job:
    job_id: str
    status: str
    product: ProductInput
    created_at: str
    updated_at: str
    stage: str = "QUEUED"
    message: str = "Queued"
    result: Mapping[str, Any] | None = None
    error: str = ""


@dataclass(slots=True)
class JobStore:
    jobs: dict[str, Job] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def put(self, job: Job) -> None:
        with self.lock:
            self.jobs[job.job_id] = job

    def get(self, job_id: str) -> Job:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return job


CONFIG: RuntimeConfig = load_config()
ORCHESTRATOR = ProductURLOrchestrator(CONFIG)
STORE = JobStore()
EXECUTOR = ThreadPoolExecutor(max_workers=max(1, int(os.getenv("PRODUCT_URL_JOB_WORKERS") or 2)))
app = FastAPI(title="Product URL Resolver", version="1.0.0")


@app.get("/health")
def health() -> dict[str, Any]:
    browser = BrowserClient.from_env(CONFIG.browser).health()
    return {
        "status": "healthy",
        "version": "1.0.0",
        "runtime_contract": CONFIG.runtime_contract,
        "browser": browser,
        "reasoning": {"enabled": CONFIG.reasoning.enabled, "required": CONFIG.reasoning.required, "model": CONFIG.reasoning.model},
        "feature_set_root": str(CONFIG.feature_set_root),
        "artifact_root": str(CONFIG.artifact_root),
        "profiles": {
            "Focused": {"search_credits": 2, "max_candidates": 6, "browser_candidates": 1},
            "Standard": {"search_credits": 3, "max_candidates": 12, "browser_candidates": 3},
            "Extended": {"search_credits": 3, "max_candidates": 24, "max_per_domain": 3, "browser_candidates": 6},
        },
    }


@app.post("/v1/resolve")
def resolve(payload: ProductPayload) -> dict[str, Any]:
    product = _product(payload)
    return to_jsonable(ORCHESTRATOR.resolve(product))


@app.post("/v1/jobs")
def create_job(payload: ProductPayload) -> dict[str, Any]:
    product = _product(payload)
    job_id = f"JOB-{uuid.uuid4().hex[:12].upper()}"
    now = _now()
    job = Job(job_id, "QUEUED", product, now, now)
    STORE.put(job)
    EXECUTOR.submit(_run_job, job_id)
    return _job_view(job)


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    try:
        return _job_view(STORE.get(job_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc


@app.get("/v1/jobs/{job_id}/result")
def get_result(job_id: str) -> dict[str, Any]:
    try:
        job = STORE.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    if job.status not in {"COMPLETED", "REVIEW_REQUIRED", "FAILED", "TECHNICAL_FAILURE"}:
        raise HTTPException(status_code=409, detail="job is not complete")
    return dict(job.result or {})


def _run_job(job_id: str) -> None:
    job = STORE.get(job_id)
    job.status = "RUNNING"
    job.updated_at = _now()

    def progress(event: RunEvent) -> None:
        job.stage = event.stage.value
        job.message = event.message
        job.updated_at = _now()

    try:
        result = ORCHESTRATOR.resolve(job.product, progress=progress)
        job.result = to_jsonable(result)
        job.status = {
            "VERIFIED": "COMPLETED",
            "REVIEW_REQUIRED": "REVIEW_REQUIRED",
            "FAILED": "FAILED",
            "TECHNICAL_FAILURE": "TECHNICAL_FAILURE",
        }[result.decision.status.value]
        job.stage = "COMPLETE" if job.status in {"COMPLETED", "REVIEW_REQUIRED"} else "FAILED"
        job.message = result.decision.reasons[0]
        job.error = result.technical_error
    except Exception as exc:
        job.status = "TECHNICAL_FAILURE"
        job.stage = "FAILED"
        job.message = "Unhandled job-service failure"
        job.error = f"{type(exc).__name__}: {exc}"
    finally:
        job.updated_at = _now()


def _product(payload: ProductPayload) -> ProductInput:
    row_id = payload.row_id or f"RUN-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    return ProductInput(
        row_id=row_id,
        main_text=payload.main_text,
        country_code=payload.country_code,
        retailer_name=payload.retailer_name,
        ean=payload.ean,
        language_code=payload.language_code,
        feature_set=payload.feature_set,
        runtime_options=payload.runtime_options,
    )


def _job_view(job: Job) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "row_id": job.product.row_id,
        "status": job.status,
        "stage": job.stage,
        "message": job.message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "error": job.error,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
