#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

build=false
case "${1:-}" in
  "") ;;
  --build) build=true ;;
  *)
    echo "Usage: $0 [--build]" >&2
    exit 2
    ;;
esac

mkdir -p data/artifacts secrets .runtime
# The bind-mount root must allow the non-root agent to create per-run setgid
# directories. Per-run directories are then restricted to the shared runtime
# group by ArtifactWriter.
chmod 1777 data/artifacts
chmod 0700 secrets

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example; add SERPAPI and PCA LLM credentials before production use."
fi

if [[ ! -s secrets/browser_api_token.txt ]]; then
  python - <<'PY' > secrets/browser_api_token.txt
import secrets
print(secrets.token_urlsafe(32))
PY
fi
chmod 0600 secrets/browser_api_token.txt

compose=(docker compose --env-file .env)

# Reconcile only this Compose project. This releases ports owned by an earlier
# product-url-resolver deployment without touching unrelated containers.
"${compose[@]}" down --remove-orphans >/dev/null 2>&1 || true

if [[ "$build" == true ]]; then
  "${compose[@]}" build
fi

started=false
for attempt in 1 2 3; do
  python scripts/resolve_ports.py --env-file .env --output .runtime/ports.env
  set -a
  # shellcheck disable=SC1091
  source .runtime/ports.env
  set +a

  log_file=".runtime/compose-up-${attempt}.log"
  if "${compose[@]}" up -d --force-recreate --remove-orphans >"$log_file" 2>&1; then
    cat "$log_file"
    started=true
    break
  fi

  cat "$log_file" >&2
  if grep -Eqi 'port is already allocated|Bind for .* failed|address already in use' "$log_file"; then
    echo "A selected port was claimed during startup; resolving a new port set (attempt $((attempt + 1))/3)." >&2
    "${compose[@]}" down --remove-orphans >/dev/null 2>&1 || true
    continue
  fi
  exit 1
done

if [[ "$started" != true ]]; then
  echo "Unable to start the stack after three dynamic port-resolution attempts." >&2
  exit 1
fi

"${compose[@]}" ps

python - "$PRODUCT_URL_HOST_PORT" "$PRODUCT_URL_UI_PORT" <<'PY'
from __future__ import annotations

import json
import sys
import time
import urllib.request

agent_port = int(sys.argv[1])
ui_port = int(sys.argv[2])

def wait(url: str, label: str, timeout: int = 180) -> None:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if 200 <= response.status < 500:
                    return
        except Exception as exc:  # startup polling must retain the latest reason
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(2)
    raise SystemExit(f"{label} did not become ready at {url}: {last_error}")

agent_url = f"http://127.0.0.1:{agent_port}"
ui_url = f"http://127.0.0.1:{ui_port}"
wait(f"{agent_url}/health", "Agent")
wait(ui_url, "UI")

with urllib.request.urlopen(f"{agent_url}/health", timeout=5) as response:
    health = json.load(response)

print("\nProduct URL Resolver is ready")
print(f"Agent health : {agent_url}/health")
print(f"API docs     : {agent_url}/docs")
print(f"UI           : {ui_url}")
print("Resolved ports: .runtime/ports.env")
print(f"Trace contract: {health.get('trace_contract') or 'unavailable'}")
reasoning = health.get("reasoning") or {}
print(
    "PCA reasoning : "
    f"enabled={reasoning.get('enabled')} "
    f"required={reasoning.get('required')} "
    f"deployment={reasoning.get('deployment') or 'not-configured'} "
    f"consumer_header_configured={reasoning.get('consumer_header_configured')}"
)
PY

if grep -Eqi '^PRODUCT_URL_REASONING_ENABLED=(false|0|no|off)[[:space:]]*$' .env \
  && grep -Eq '^PCA_LLM_ENDPOINT=.+$' .env; then
  echo
  echo "WARNING: PCA credentials are configured, but PRODUCT_URL_REASONING_ENABLED=false; the LLM will not be called." >&2
fi
