from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.product_evidence_harness.runtime_contract import (  # noqa: E402
    REQUIRED_RUNTIME_CAPABILITIES,
    RUNTIME_CONTRACT_VERSION,
)


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        values[key] = value.strip().strip('"').strip("'")
    return values


def extract_configuration_error(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    detail = payload.get("detail")
    if isinstance(detail, dict):
        value = detail.get("configuration_error")
        return str(value) if value else None
    return None


def runtime_contract_error(payload: dict[str, Any]) -> str | None:
    running = str(payload.get("runtime_contract_version") or "").strip()
    if running != RUNTIME_CONTRACT_VERSION:
        return (
            "Agent runtime contract mismatch: "
            f"expected={RUNTIME_CONTRACT_VERSION}, running={running or 'missing/legacy'}"
        )
    missing = [
        label
        for key, label in REQUIRED_RUNTIME_CAPABILITIES.items()
        if not payload.get(key)
    ]
    if missing:
        return "Agent runtime capabilities missing: " + ", ".join(missing)
    return None


def write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait for the product-evidence stack to become notebook-ready")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--url")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--write-status", default="data/runtime/stack_health.json")
    args = parser.parse_args()

    values = parse_env_file(Path(args.env_file))
    port = os.getenv("AGENT_HOST_PORT") or values.get("AGENT_HOST_PORT") or "8788"
    url = args.url or os.getenv("PRODUCT_AGENT_URL") or f"http://127.0.0.1:{port}/health"
    timeout = args.timeout or float(
        os.getenv("STACK_STARTUP_TIMEOUT_SECONDS")
        or values.get("STACK_STARTUP_TIMEOUT_SECONDS")
        or "300"
    )
    status_path = Path(args.write_status) if args.write_status else None

    deadline = time.monotonic() + timeout
    next_progress = 0.0
    last_error = "No response received"
    print(f"Waiting for notebook-ready agent health at {url}")
    print(f"Expected runtime contract: {RUNTIME_CONTRACT_VERSION}")

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                body = response.read().decode("utf-8", errors="replace")
                payload = json.loads(body)
                if 200 <= response.status < 300 and payload.get("status") == "healthy":
                    contract_error = runtime_contract_error(payload)
                    if contract_error:
                        write_json(status_path, payload)
                        print(contract_error, file=sys.stderr)
                        print(
                            "Rebuild from this checkout with: ./scripts/azureml_startup.sh --clean-build",
                            file=sys.stderr,
                        )
                        return 3
                    write_json(status_path, payload)
                    print(json.dumps(payload, indent=2, sort_keys=True))
                    print("Stack is healthy and notebook-ready. Runtime contract is compatible.")
                    return 0
                last_error = f"HTTP {response.status}: {body[:1000]}"
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = {"raw": body}
            configuration_error = extract_configuration_error(payload)
            if configuration_error:
                print("Agent configuration validation failed:", file=sys.stderr)
                print(configuration_error, file=sys.stderr)
                print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stderr)
                return 2
            last_error = f"HTTP {exc.code}: {body[:1000]}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        now = time.monotonic()
        if now >= next_progress:
            remaining = max(0, int(deadline - now))
            print(f"Stack is starting; {remaining}s remaining. Last observation: {last_error}")
            next_progress = now + 15
        time.sleep(3)

    print(f"Stack did not become healthy within {timeout:.0f}s. Last observation: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
