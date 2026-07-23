from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from product_url_v2.browser import BrowserClient
from product_url_v2.config import RuntimeConfig, load_config
from product_url_v2.models import ProductInput, RunEvent, to_jsonable
from product_url_v2.orchestrator import ProductURLOrchestrator
from product_url_v2.policy import ACCEPTANCE_POLICY_VERSION, SOURCE_PRIORITY
from product_url_v2.trace import TRACE_CONTRACT, TRACE_NOTICE

VERSION = "1.3.0"
TERMINAL_JOB_STATUSES = {"COMPLETED", "REVIEW_REQUIRED", "FAILED", "TECHNICAL_FAILURE"}


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
    events: list[RunEvent] = field(default_factory=list)


@dataclass(slots=True)
class JobStore:
    jobs: dict[str, Job] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)

    def put(self, job: Job) -> None:
        with self.lock:
            self.jobs[job.job_id] = job

    def mark_running(self, job_id: str) -> ProductInput:
        with self.lock:
            job = self._require(job_id)
            job.status = "RUNNING"
            job.stage = "INTERPRET"
            job.message = "Starting exact product-to-URL mapping."
            job.updated_at = _now()
            return job.product

    def record_event(self, job_id: str, event: RunEvent) -> None:
        with self.lock:
            job = self._require(job_id)
            if not job.events or job.events[-1].sequence < event.sequence:
                job.events.append(event)
            job.stage = event.stage.value
            job.message = event.message
            job.updated_at = _now()

    def finish(self, job_id: str, result: Mapping[str, Any], status: str, message: str) -> None:
        with self.lock:
            job = self._require(job_id)
            job.result = dict(result)
            job.status = status
            job.message = message
            job.updated_at = _now()

    def fail(self, job_id: str, error: str) -> None:
        with self.lock:
            job = self._require(job_id)
            job.status = "TECHNICAL_FAILURE"
            job.stage = "FAILED"
            job.error = error
            job.message = error
            job.updated_at = _now()

    def view(self, job_id: str) -> dict[str, Any]:
        with self.lock:
            return _job_view(self._require(job_id))

    def trace(self, job_id: str, after_sequence: int = 0) -> dict[str, Any]:
        with self.lock:
            return _trace_view(self._require(job_id), after_sequence=after_sequence)

    def result(self, job_id: str) -> dict[str, Any]:
        with self.lock:
            job = self._require(job_id)
            if job.status not in TERMINAL_JOB_STATUSES:
                raise RuntimeError("job is not complete")
            return dict(job.result or {})

    def _require(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job


CONFIG: RuntimeConfig = load_config()
ORCHESTRATOR = ProductURLOrchestrator(CONFIG)
STORE = JobStore()
EXECUTOR = ThreadPoolExecutor(max_workers=max(1, int(os.getenv("PRODUCT_URL_JOB_WORKERS") or 2)))
app = FastAPI(title="Exact Product Mapping Resolver", version=VERSION)


@app.get("/health")
def health() -> dict[str, Any]:
    browser = BrowserClient.from_env(CONFIG.browser).health()
    source_priority = [
        role
        for role, _ in sorted(SOURCE_PRIORITY.items(), key=lambda item: item[1], reverse=True)
    ]
    return {
        "status": "healthy",
        "version": VERSION,
        "runtime_contract": CONFIG.runtime_contract,
        "acceptance_policy": ACCEPTANCE_POLICY_VERSION,
        "acceptance_policy_module": "product_url_v2.policy",
        "source_priority": source_priority,
        "trace_contract": TRACE_CONTRACT,
        "trace_notice": TRACE_NOTICE,
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
            "Focused": {"search_credits": 2, "max_candidates": 8, "browser_candidates": 3, "browser_required": True},
            "Standard": {"search_credits": 3, "max_candidates": 16, "browser_candidates": 6, "browser_required": True},
            "Extended": {"search_credits": 3, "max_candidates": 30, "max_per_domain": 4, "browser_candidates": 10, "browser_required": True},
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
    STORE.put(Job(job_id, "QUEUED", product, now, now))
    EXECUTOR.submit(_run_job, job_id)
    return STORE.view(job_id)


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    try:
        return STORE.view(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc


@app.get("/v1/jobs/{job_id}/trace")
def get_trace(job_id: str, after_sequence: int = Query(default=0, ge=0)) -> dict[str, Any]:
    try:
        return STORE.trace(job_id, after_sequence=after_sequence)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc


@app.get("/v1/jobs/{job_id}/result")
def get_result(job_id: str) -> dict[str, Any]:
    try:
        return STORE.result(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _run_job(job_id: str) -> None:
    try:
        product = STORE.mark_running(job_id)

        def progress(event: RunEvent) -> None:
            STORE.record_event(job_id, event)

        result = ORCHESTRATOR.resolve(product, progress=progress)
        rendered = to_jsonable(result)
        status = {
            "VERIFIED": "COMPLETED",
            "REVIEW_REQUIRED": "REVIEW_REQUIRED",
            "FAILED": "FAILED",
            "TECHNICAL_FAILURE": "TECHNICAL_FAILURE",
        }[result.decision.status.value]
        STORE.finish(job_id, rendered, status, result.decision.status.value)
    except Exception as exc:
        STORE.fail(job_id, f"{type(exc).__name__}: {exc}")


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
    last_sequence = job.events[-1].sequence if job.events else 0
    return {
        "job_id": job.job_id,
        "status": job.status,
        "stage": job.stage,
        "message": job.message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "row_id": job.product.row_id,
        "error": job.error or None,
        "event_count": len(job.events),
        "last_event_sequence": last_sequence,
        "trace_contract": TRACE_CONTRACT,
        "trace_url": f"/v1/jobs/{job.job_id}/trace",
    }


def _trace_view(job: Job, *, after_sequence: int = 0) -> dict[str, Any]:
    events = [event for event in job.events if event.sequence > after_sequence]
    return {
        "job_id": job.job_id,
        "status": job.status,
        "stage": job.stage,
        "message": job.message,
        "event_count": len(job.events),
        "last_event_sequence": job.events[-1].sequence if job.events else 0,
        "trace_contract": TRACE_CONTRACT,
        "notice": TRACE_NOTICE,
        "events": to_jsonable(events),
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
