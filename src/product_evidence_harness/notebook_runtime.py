from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

AGENT_URL = os.getenv("PRODUCT_AGENT_URL", "http://127.0.0.1:8788").rstrip("/")
POLL_SECONDS = 3
HEARTBEAT_SECONDS = 30
TERMINAL_STATUSES = {"COMPLETED", "REVIEW_REQUIRED", "FAILED"}
DEFAULT_FEATURE_SET = "toy_features"


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "docker-compose.yml").is_file() and (candidate / "notebooks").is_dir():
            return candidate
    raise RuntimeError("Could not locate the repository root containing docker-compose.yml")


def api_json(method: str, path: str, payload: dict | None = None, timeout: int = 30) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{AGENT_URL}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Agent API returned HTTP {exc.code}: {detail}\n"
            "Run ./scripts/azureml_startup.sh and rerun the readiness cell."
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            f"Cannot reach {AGENT_URL}. Run ./scripts/azureml_startup.sh first."
        ) from exc


def check_health() -> dict:
    health = api_json("GET", "/health", timeout=15)
    if health.get("status") != "healthy":
        raise RuntimeError(f"Platform is not healthy: {json.dumps(health, indent=2)}")
    configuration = health.get("configuration") or {}
    required = {
        "three_stage_contract_enforced": "three-credit contract",
        "adaptive_search_contract_enforced": "adaptive multi-engine search",
        "llm_search_planning_enabled": "LLM search planning",
        "llm_search_feedback_enabled": "LLM search feedback",
        "agentic_browser_contract_enforced": "agentic browser contract",
        "llm_configured": "LLM configuration",
    }
    missing = [label for key, label in required.items() if not configuration.get(key)]
    if configuration.get("serpapi_request_limit") != 3:
        missing.append("exact three-credit SerpAPI limit")
    if missing:
        raise RuntimeError("Platform contract missing: " + ", ".join(missing))
    browser = health.get("browser_service") or {}
    if not browser.get("agentic_tools"):
        raise RuntimeError("Browser service does not expose agentic session tools")
    return health


def submit_product(product: dict, feature_set: str = DEFAULT_FEATURE_SET) -> str:
    return api_json("POST", "/v1/jobs", {"product": product, "feature_set": feature_set})["job_id"]


def wait_for_job(
    job_id: str,
    poll_seconds: int = POLL_SECONDS,
    heartbeat_seconds: int = HEARTBEAT_SECONDS,
) -> dict:
    started = time.monotonic()
    last_signature = None
    last_printed_at = 0.0
    while True:
        status = api_json("GET", f"/v1/jobs/{job_id}", timeout=15)
        signature = (status.get("status"), status.get("stage"), status.get("message"))
        now = time.monotonic()
        elapsed = int(now - started)
        if signature != last_signature or now - last_printed_at >= heartbeat_seconds:
            line = f"{job_id}: {status['status']} | {status.get('stage', '')} | {status.get('message', '')}"
            if signature == last_signature:
                line += f" | still running ({elapsed}s elapsed)"
            print(line)
            last_signature = signature
            last_printed_at = now
        if status["status"] in TERMINAL_STATUSES:
            if status["status"] == "FAILED":
                raise RuntimeError(status.get("error") or status.get("message") or "Job failed")
            return status
        time.sleep(poll_seconds)


def run_product(product: dict, feature_set: str = DEFAULT_FEATURE_SET) -> dict:
    job_id = submit_product(product, feature_set)
    wait_for_job(job_id)
    return api_json("GET", f"/v1/jobs/{job_id}/result", timeout=60)


def host_artifact_dir(project_root: Path, result: dict) -> Path | None:
    row_id = (result.get("product") or {}).get("row_id")
    return project_root / "data" / "artifacts" / row_id if row_id else None
