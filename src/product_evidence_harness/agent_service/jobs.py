from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"


@dataclass
class JobRecord:
    job_id: str
    status: JobStatus
    stage: str
    created_at: str
    updated_at: str
    payload: dict[str, Any]
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self, *, include_payload: bool = False, include_result: bool = False) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        if not include_payload:
            data.pop("payload", None)
        if not include_result:
            data.pop("result", None)
        return data


class InMemoryJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.RLock()

    def create(self, payload: dict[str, Any], requested_id: str | None = None) -> JobRecord:
        now = self._now()
        prefix = requested_id or str(payload.get("row_id") or "job")
        job_id = f"{prefix}-{uuid.uuid4().hex[:10]}"
        record = JobRecord(
            job_id=job_id,
            status=JobStatus.QUEUED,
            stage="VALIDATING_INPUT",
            created_at=now,
            updated_at=now,
            payload=dict(payload),
        )
        with self._lock:
            self._jobs[job_id] = record
        return record

    def get(self, job_id: str) -> JobRecord:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return self._jobs[job_id]

    def update(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        stage: str | None = None,
        message: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> JobRecord:
        with self._lock:
            record = self.get(job_id)
            if status is not None:
                record.status = status
            if stage is not None:
                record.stage = stage
            if message is not None:
                record.message = message
            if result is not None:
                record.result = result
            if error is not None:
                record.error = error
            record.updated_at = self._now()
            return record

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
