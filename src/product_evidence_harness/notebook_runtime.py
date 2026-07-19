from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.product_evidence_harness.runtime_contract import (
    REQUIRED_RESULT_FIELDS,
    REQUIRED_RESULT_KEYS,
    REQUIRED_RUNTIME_CAPABILITIES,
    RUNTIME_CONTRACT_VERSION,
)

AGENT_URL = os.getenv("PRODUCT_AGENT_URL", "http://127.0.0.1:8788").rstrip("/")
POLL_SECONDS = 3
HEARTBEAT_SECONDS = 30
TERMINAL_STATUSES = {"COMPLETED", "REVIEW_REQUIRED", "FAILED"}
DEFAULT_FEATURE_SET = "toy_features"


@dataclass(frozen=True)
class PlatformRecovery:
    attempted: bool
    recovered: bool
    clean_build: bool
    command: tuple[str, ...]
    trigger: str = ""
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _enabled(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


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
            "Run ./scripts/azureml_startup.sh --clean-build and rerun the readiness cell."
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            f"Cannot reach {AGENT_URL}. Run ./scripts/azureml_startup.sh --clean-build first."
        ) from exc


def _nested_value(payload: dict, dotted_path: str):
    value = payload
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _health_contract_error(health: dict) -> str | None:
    if health.get("status") != "healthy":
        return "Platform is not healthy: " + json.dumps(health, indent=2, default=str)[:4000]

    running_contract = str(health.get("runtime_contract_version") or "").strip()
    if running_contract != RUNTIME_CONTRACT_VERSION:
        return (
            "STALE_AGENT_IMAGE: notebook code and the running Docker agent do not match.\n"
            f"Notebook expects: {RUNTIME_CONTRACT_VERSION}\n"
            f"Running agent reports: {running_contract or 'missing/legacy'}"
        )

    missing_runtime = [
        label
        for key, label in REQUIRED_RUNTIME_CAPABILITIES.items()
        if not health.get(key)
    ]
    if missing_runtime:
        return "Agent runtime capabilities missing: " + ", ".join(missing_runtime)

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
        return "Platform contract missing: " + ", ".join(missing)

    browser = health.get("browser_service") or {}
    if not browser.get("agentic_tools"):
        return "Browser service does not expose agentic session tools"
    return None


def check_health() -> dict:
    health = api_json("GET", "/health", timeout=15)
    error = _health_contract_error(health)
    if error:
        raise RuntimeError(
            error
            + "\n\nRecovery command:\n"
            + "  ./scripts/azureml_startup.sh --clean-build\n"
            + "Restart the notebook kernel only if local imports remain stale after recovery."
        )
    return health


def _recoverable_platform_error(exc: Exception) -> bool:
    message = str(exc)
    return any(
        marker in message
        for marker in (
            "STALE_AGENT_IMAGE",
            "Cannot reach",
            "Platform is not healthy",
            "Agent runtime capabilities missing",
            "Browser service does not expose",
        )
    )


def recover_platform(
    project_root: str | Path,
    *,
    clean_build: bool = True,
    timeout_seconds: int = 1800,
) -> PlatformRecovery:
    root = Path(project_root).resolve()
    script = root / "scripts" / "azureml_startup.sh"
    if not script.is_file():
        raise FileNotFoundError(f"Azure ML startup script not found: {script}")

    command = [str(script)]
    if clean_build:
        command.append("--clean-build")

    print("Recovering the local Azure ML product-evidence runtime...")
    print("Command:", " ".join(command))
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    tail: list[str] = []
    try:
        assert process.stdout is not None
        while True:
            line = process.stdout.readline()
            if line:
                print(line, end="")
                tail.append(line.rstrip())
                tail = tail[-80:]
            if process.poll() is not None:
                for remaining in process.stdout:
                    print(remaining, end="")
                    tail.append(remaining.rstrip())
                    tail = tail[-80:]
                break
            if time.monotonic() - started > timeout_seconds:
                process.terminate()
                raise TimeoutError(
                    f"Platform recovery exceeded {timeout_seconds}s. Last output:\n"
                    + "\n".join(tail)
                )
    finally:
        if process.poll() is None:
            process.kill()

    elapsed = time.monotonic() - started
    if process.returncode != 0:
        raise RuntimeError(
            f"Azure ML runtime recovery failed with exit code {process.returncode}.\n"
            + "\n".join(tail)
        )

    return PlatformRecovery(
        attempted=True,
        recovered=True,
        clean_build=clean_build,
        command=tuple(command),
        elapsed_seconds=round(elapsed, 2),
    )


def ensure_platform_ready(
    project_root: str | Path,
    *,
    auto_recover: bool | None = None,
    clean_build: bool | None = None,
) -> tuple[dict, PlatformRecovery]:
    auto_recover = (
        _enabled("PRODUCT_HARNESS_NOTEBOOK_AUTO_RECOVER_PLATFORM", True)
        if auto_recover is None
        else auto_recover
    )
    clean_build = (
        _enabled("PRODUCT_HARNESS_NOTEBOOK_CLEAN_BUILD_ON_RECOVERY", True)
        if clean_build is None
        else clean_build
    )
    try:
        return check_health(), PlatformRecovery(
            attempted=False,
            recovered=False,
            clean_build=clean_build,
            command=(),
        )
    except Exception as exc:
        if not auto_recover or not _recoverable_platform_error(exc):
            raise
        recovery = recover_platform(project_root, clean_build=clean_build)
        health = check_health()
        return health, PlatformRecovery(
            attempted=True,
            recovered=True,
            clean_build=recovery.clean_build,
            command=recovery.command,
            trigger=str(exc).splitlines()[0][:500],
            elapsed_seconds=recovery.elapsed_seconds,
        )


def validate_result_contract(result: dict) -> dict:
    missing = [path for path in REQUIRED_RESULT_FIELDS if _nested_value(result, path) is None]
    missing_keys = [key for key in REQUIRED_RESULT_KEYS if key not in result]
    missing.extend(missing_keys)
    if missing:
        raise RuntimeError(
            "RESULT_CONTRACT_MISMATCH: agent response is missing required fields: "
            + ", ".join(missing)
            + ". Re-run the notebook readiness cell to verify the agent image."
        )

    delivery = result.get("url_delivery") or {}
    primary_url = str(result.get("primary_url") or "").strip()
    if not primary_url or not delivery.get("delivered"):
        product_match = result.get("product_match") or {}
        raise RuntimeError(
            "MANDATORY_PRODUCT_URL_NOT_DELIVERED\n"
            f"job_status={result.get('job_status')}\n"
            f"delivery_status={delivery.get('status')}\n"
            f"match_reason={product_match.get('match_reason')}\n"
            f"best_available_url={product_match.get('best_available_url')}\n"
            f"artifact_dir={result.get('artifact_dir')}\n"
            "Inspect mandatory_url_delivery.json, source_selection.json, and candidates.csv "
            "in the artifact directory."
        )
    return result


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
    check_health()
    job_id = submit_product(product, feature_set)
    wait_for_job(job_id)
    return validate_result_contract(
        api_json("GET", f"/v1/jobs/{job_id}/result", timeout=60)
    )


def host_artifact_dir(project_root: Path, result: dict) -> Path | None:
    row_id = (result.get("product") or {}).get("row_id")
    return project_root / "data" / "artifacts" / row_id if row_id else None
