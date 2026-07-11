from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

PLACEHOLDER_MARKERS = (
    "replace_",
    "replace-",
    "example",
    "placeholder",
    "changeme",
    "change_me",
    "<",
    ">",
)
TRUE_VALUES = {"1", "true", "yes", "on"}
ENV_ASSIGNMENT = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


class PreflightError(RuntimeError):
    pass


def parse_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise PreflightError(".env is missing. Run: cp .env.example .env")
    if path.is_symlink():
        raise PreflightError(".env must be a regular file, not a symlink")
    if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PreflightError(".env permissions are too broad. Run: chmod 600 .env")

    values: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = ENV_ASSIGNMENT.match(line)
        if not match:
            raise PreflightError(f"Malformed .env assignment at line {line_number}")
        key, value = match.groups()
        if key in values:
            raise PreflightError(f"Duplicate .env key: {key}")
        values[key] = value.strip().strip('"').strip("'")
    return values


def is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return not lowered or any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def is_enabled(values: dict[str, str], key: str, default: bool = False) -> bool:
    raw = values.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in TRUE_VALUES


def validate_env(values: dict[str, str]) -> None:
    if values.get("PRODUCT_HARNESS_WORKFLOW", "one_credit_feature_aware") != "one_credit_feature_aware":
        raise PreflightError("PRODUCT_HARNESS_WORKFLOW must be one_credit_feature_aware")
    if values.get("PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES", "1") != "1":
        raise PreflightError("PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES must be 1")
    if values.get("PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES", "0") != "0":
        raise PreflightError("PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES must be 0")

    serp_key = values.get("SERPAPI_API_KEY", "")
    if len(serp_key) < 20 or is_placeholder(serp_key):
        raise PreflightError("SERPAPI_API_KEY is missing or still contains the example value")

    vision_enabled = is_enabled(values, "PRODUCT_HARNESS_ENABLE_VISION_REASONING", True)
    text_llm_enabled = is_enabled(values, "PRODUCT_HARNESS_ENABLE_LLM_FEATURE_REASONING", False)
    if vision_enabled or text_llm_enabled:
        required = ("LLM_API_KEY", "LLM_API_VERSION", "LLM_ENDPOINT", "LLM_DEPLOYMENT")
        missing = [key for key in required if is_placeholder(values.get(key, ""))]
        if missing:
            raise PreflightError("LLM configuration is missing or still contains examples: " + ", ".join(missing))
        endpoint = values["LLM_ENDPOINT"]
        if not endpoint.startswith("https://"):
            raise PreflightError("LLM_ENDPOINT must use HTTPS")


def validate_feature_file(path: Path) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PreflightError(f"Invalid feature JSON: {path}: {exc}") from exc
    if set(payload) != {"features_to_code"}:
        raise PreflightError(f"{path} must contain only the top-level key features_to_code")
    features = payload.get("features_to_code")
    if not isinstance(features, list) or not features:
        raise PreflightError(f"{path} must contain a non-empty features_to_code list")
    for index, item in enumerate(features):
        if isinstance(item, str):
            valid = bool(item.strip())
        elif isinstance(item, dict):
            valid = set(item).issubset({"name", "description"}) and bool(str(item.get("name", "")).strip())
        else:
            valid = False
        if not valid:
            raise PreflightError(f"Invalid feature entry {index} in {path}")


def ensure_feature_set(project_dir: Path) -> list[Path]:
    private_root = project_dir / "inputs" / "private"
    private_root.mkdir(parents=True, exist_ok=True)
    files = sorted(private_root.glob("*.json"))
    if not files:
        example = project_dir / "examples" / "features_to_code.example.json"
        if not example.is_file():
            raise PreflightError("No private feature set exists and the example feature file is missing")
        target = private_root / "example_features.json"
        shutil.copyfile(example, target)
        files = [target]
        print("Created inputs/private/example_features.json from the generic example.")
    for path in files:
        validate_feature_file(path)
    return files


def run_checked(command: list[str], cwd: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        message = detail[-1] if detail else "unknown error"
        raise PreflightError(f"Command failed: {' '.join(command)}: {message}")


def check_docker(project_dir: Path) -> None:
    if shutil.which("docker") is None:
        raise PreflightError("Docker is not installed or is not available on PATH")
    run_checked(["docker", "info"], project_dir)
    run_checked(["docker", "compose", "version"], project_dir)
    run_checked(["docker", "compose", "config", "--quiet"], project_dir)


def check_agent_port(values: dict[str, str]) -> None:
    port = int(values.get("AGENT_HOST_PORT", "8788"))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        occupied = sock.connect_ex(("127.0.0.1", port)) == 0
    if not occupied:
        return
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
            if 200 <= response.status < 300:
                print(f"Agent port {port} is already serving a healthy platform; startup is idempotent.")
                return
    except (URLError, TimeoutError):
        pass
    raise PreflightError(f"Port {port} is already in use by another process")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a fresh Azure ML checkout before Docker Compose startup")
    parser.add_argument("--project-dir", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--skip-docker", action="store_true", help="Used only by unit tests")
    parser.add_argument("--skip-port", action="store_true", help="Used only by unit tests")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    values = parse_env(project_dir / ".env")
    validate_env(values)
    feature_files = ensure_feature_set(project_dir)
    (project_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (project_dir / "secrets").mkdir(parents=True, exist_ok=True)
    if not args.skip_port:
        check_agent_port(values)
    if not args.skip_docker:
        check_docker(project_dir)

    print("Preflight passed.")
    print(f"Validated feature sets: {len(feature_files)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PreflightError as exc:
        print(f"PRECHECK FAILED: {exc}", file=sys.stderr)
        raise SystemExit(2)
