from __future__ import annotations

import json
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException

from src.product_evidence_harness.compat_patches import (
    apply_compatibility_patches,
    compatibility_patches_applied,
)
from src.product_evidence_harness.numeric_safety import safe_int
from src.product_evidence_harness.runtime_contract import runtime_capabilities
from src.product_evidence_harness.runtime_controls import (
    normalize_runtime_controls,
    runtime_control_catalog,
)

apply_compatibility_patches()

from src.product_evidence_harness.agent_service.jobs import InMemoryJobStore, JobStatus
from src.product_evidence_harness.agent_service.strict_orchestrator import (
    StrictProductEvidenceOrchestrator,
)
from src.product_evidence_harness.llm.service import LLMConfig
from src.product_evidence_harness.progress_context import browser_progress_callback
from src.product_evidence_harness.three_stage_environment import validate_runtime_environment


app = FastAPI(title="Product Evidence Agent", version="1.0.0")
store = InMemoryJobStore()
executor = ThreadPoolExecutor(
    max_workers=safe_int(
        os.getenv("AGENT_WORKERS"),
        2,
        minimum=1,
        maximum=32,
        field_name="AGENT_WORKERS",
    )
)
orchestrator = StrictProductEvidenceOrchestrator()


def _enabled(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _validate_runtime() -> tuple[dict | None, str | None]:
    try:
        report = validate_runtime_environment(None, strict_file_permissions=False)
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


def _service_health() -> dict:
    return {
        **dict(orchestrator.health()),
        **runtime_capabilities(),
        "compatibility_patches_applied": compatibility_patches_applied(),
        "agent_entrypoint": "src.product_evidence_harness.agent_service.app:app",
        "runtime_control_catalog": runtime_control_catalog(),
    }


@app.get("/health")
def health() -> dict:
    configuration, configuration_error = _validate_runtime()
    service = _service_health()
    if not service.get("compatibility_patches_applied"):
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "configuration_error": "Agent compatibility patches were not initialized",
                "browser_service": service.get("browser_service"),
                **runtime_capabilities(),
            },
        )
    if configuration_error:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "configuration_error": configuration_error,
                "browser_service": service.get("browser_service"),
                **runtime_capabilities(),
                "compatibility_patches_applied": True,
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

    try:
        normalized_options = normalize_runtime_controls(payload.get("runtime_options"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    normalized_payload = dict(payload)
    if normalized_options:
        normalized_payload["runtime_options"] = normalized_options
    else:
        normalized_payload.pop("runtime_options", None)

    product = normalized_payload.get("product")
    if not isinstance(product, dict):
        raise HTTPException(
            status_code=422,
            detail="product must be an object containing row_id, main_text and country_code",
        )

    row_id = str(product.get("row_id") or "").strip()
    main_text = str(product.get("main_text") or "").strip()
    country_code = str(product.get("country_code") or "").strip()
    feature_set = str(normalized_payload.get("feature_set") or "").strip()
    missing = [
        name
        for name, value in (
            ("product.row_id", row_id),
            ("product.main_text", main_text),
            ("product.country_code", country_code),
            ("feature_set", feature_set),
        )
        if not value
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail="Missing mandatory field(s): " + ", ".join(missing),
        )

    record = store.create(normalized_payload, requested_id=row_id)
    executor.submit(_run_job, record.job_id)
    return {
        "job_id": record.job_id,
        "status": record.status.value,
        "runtime_options": normalized_options,
    }


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


def _write_failure_diagnostic(record, exc: Exception) -> str | None:
    product = record.payload.get("product") if isinstance(record.payload, dict) else None
    row_id = str((product or {}).get("row_id") or "").strip()
    if not row_id:
        return None

    try:
        root = Path(orchestrator.config.artifact_root) / row_id
        root.mkdir(parents=True, exist_ok=True)
        path = root / "technical_failure.json"
        temporary = path.with_suffix(".json.tmp")
        payload = {
            "schema_version": "technical-failure-v1",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "job_id": record.job_id,
            "row_id": row_id,
            "stage": record.stage,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc(),
            "action": (
                "Inspect the first project frame in traceback, correct that boundary, "
                "then rerun with a new row_id."
            ),
        }
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        return str(path)
    except Exception:
        return None


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
        latest = store.get(job_id)
        diagnostic_path = _write_failure_diagnostic(latest, exc)
        error = f"{type(exc).__name__}: {exc}"
        if diagnostic_path:
            error += f" | diagnostic={diagnostic_path}"
        store.update(
            job_id,
            status=JobStatus.FAILED,
            stage="FAILED",
            message="Product evidence workflow failed",
            error=error,
        )
