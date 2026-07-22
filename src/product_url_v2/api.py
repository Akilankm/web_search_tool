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
app = FastAPI(title="Product URL Resolver", version="1.0.1")


@app.get("/health")
def health() -> dict[str, Any]:
    browser = BrowserClient.from_env(CONFIG.browser).health()
    return {
        "status": "healthy",
        "version": "1.0.1",
        "runtime_contract": CONFIG.runtime_contract,
        "browser": browser,
        "reasoning": {
            "enabled": CONFIG.reasoning.enabled,
            "required": CONFIG.reasoning.required,
            "provider": "azure_openai_compatible",
            "deployment": CONFIG.reasoning.deployment,
            "api_version": CONFIG.reasoning.api_version,
            "consumer_header_configured": bool(CONFIG.reasoning.consumer_id),
        },
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
        job.message = result.decision.status.value
    except Exception as exc:
        job.status = "TECHNICAL_FAILURE"
        job.error = f"{type(exc).__name__}: {exc}"
        job.message = job.error
    finally:
        job.updated_at = _now()


def _product(payload: ProductPayload) -> ProductInput:
    return ProductInput(
        row_id=payload.row_id or f"RUN-{uuid.uuid4().hex[:12].upper()}",
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
        "status": job.status,
        "stage": job.stage,
        "message": job.message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "row_id": job.product.row_id,
        "error": job.error or None,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
