#!/usr/bin/env bash
set -euo pipefail

INVOKING_PWD="${PWD:-}"
PROJECT_DIR="${PRODUCT_EVIDENCE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_PERMISSION_MODE="${PRODUCT_EVIDENCE_ENV_PERMISSION_MODE:-auto}"
BUILD_IMAGES=true
STARTUP_SUCCEEDED=false

usage() {
  cat <<'EOF'
Usage: ./scripts/azureml_startup.sh [options]

Fresh Azure ML workflow:
  1. cp .env.example .env
  2. edit .env with real SerpAPI and LLM values
  3. ./scripts/azureml_startup.sh
  4. open notebooks/01_run_product_evidence.ipynb

Options:
  --no-build                 Reuse existing local images.
  --strict-env-permissions   Require .env mode 0600; disable Azure ML fallback.
  --allow-insecure-env-permissions
                             Deprecated compatibility override. Normally unnecessary.
  -h, --help                 Show this help message.
EOF
}

phase() {
  printf '\n==> %s\n' "$1"
}

is_azureml_managed_workspace() {
  local candidate normalized
  for candidate in \
    "$PROJECT_DIR" \
    "$INVOKING_PWD" \
    "${HOME:-}" \
    "${AZUREML_ROOT_DIR:-}" \
    "${AZUREML_CR_COMPUTE_CONTEXT:-}"; do
    [[ -n "$candidate" ]] || continue
    normalized="$(printf '%s' "$candidate" | tr '[:upper:]' '[:lower:]')"
    case "$normalized" in
      *"/cloudfiles/"*|*"/cloudfiles"|*"/mnt/batch/tasks/shared/ls_root/mounts/"*)
        return 0
        ;;
    esac
  done

  [[ -n "${AZUREML_COMPUTE_RESOURCE_ID:-}" || -n "${AZUREML_WORKSPACE_ID:-}" ]]
}

show_failure_diagnostics() {
  local exit_code=$?
  if [[ "$STARTUP_SUCCEEDED" == "true" || "$exit_code" == "0" ]]; then
    return
  fi
  echo >&2
  echo "Azure ML bootstrap failed. Diagnostic container state follows." >&2
  docker compose ps >&2 2>/dev/null || true
  docker compose logs --tail=200 agent browser >&2 2>/dev/null || true
}
trap show_failure_diagnostics EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build)
      BUILD_IMAGES=false
      shift
      ;;
    --strict-env-permissions)
      ENV_PERMISSION_MODE="strict"
      shift
      ;;
    --allow-insecure-env-permissions)
      ENV_PERMISSION_MODE="allow"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "$PROJECT_DIR"

phase "Preparing the fresh checkout"
if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env 2>/dev/null || true
  cat >&2 <<'EOF'
Created .env from .env.example.
Edit the real SerpAPI and LLM values, then run this same startup command again:

  ./scripts/azureml_startup.sh
EOF
  exit 2
fi

mkdir -p data/artifacts data/runtime inputs/private secrets

if [[ ! -s secrets/browser_api_token.txt ]]; then
  python - <<'PY'
from pathlib import Path
import secrets

path = Path("secrets/browser_api_token.txt")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
try:
    path.chmod(0o600)
except OSError:
    pass
PY
fi

if [[ -n "${PRODUCT_EVIDENCE_RUNTIME_UID:-}" ]]; then
  RUNTIME_UID="$PRODUCT_EVIDENCE_RUNTIME_UID"
elif [[ "$(id -u)" != "0" ]]; then
  RUNTIME_UID="$(id -u)"
else
  RUNTIME_UID="$(stat -c '%u' "$PROJECT_DIR")"
fi

if [[ -n "${PRODUCT_EVIDENCE_RUNTIME_GID:-}" ]]; then
  RUNTIME_GID="$PRODUCT_EVIDENCE_RUNTIME_GID"
elif [[ "$(id -u)" != "0" ]]; then
  RUNTIME_GID="$(id -g)"
else
  RUNTIME_GID="$(stat -c '%g' "$PROJECT_DIR")"
fi

export RUNTIME_UID RUNTIME_GID
if [[ "$RUNTIME_UID" == "0" ]]; then
  echo "Refusing to run application containers as root. Set PRODUCT_EVIDENCE_RUNTIME_UID/GID to the Azure ML notebook user." >&2
  exit 1
fi

for runtime_path in data/artifacts data/runtime; do
  probe="$runtime_path/.write-test-$$"
  if ! : > "$probe"; then
    echo "Runtime directory is not writable by the current user: $PROJECT_DIR/$runtime_path" >&2
    exit 1
  fi
  rm -f "$probe"
done

if [[ "$ENV_PERMISSION_MODE" == "auto" ]] && is_azureml_managed_workspace; then
  ENV_PERMISSION_MODE="allow"
  echo "Azure ML managed workspace detected; .env mode fallback will be applied automatically only if chmod 600 cannot be preserved."
fi

phase "Validating credentials, feature schemas, Docker, and production controls"
python scripts/preflight_azureml.py \
  --project-dir "$PROJECT_DIR" \
  --env-permission-mode "$ENV_PERMISSION_MODE" \
  --skip-port

phase "Removing stale containers from this Compose project"
docker compose down --remove-orphans

phase "Confirming the configured agent port is available"
python scripts/preflight_azureml.py \
  --project-dir "$PROJECT_DIR" \
  --env-permission-mode "$ENV_PERMISSION_MODE" \
  --skip-docker

phase "Building and starting the agent and browser services"
compose_args=(up -d --force-recreate --remove-orphans)
if [[ "$BUILD_IMAGES" == "true" ]]; then
  compose_args+=(--build)
fi
docker compose "${compose_args[@]}"

phase "Waiting for strict agent, browser, SerpAPI, and LLM readiness"
python scripts/wait_for_stack.py \
  --env-file "$PROJECT_DIR/.env" \
  --write-status "$PROJECT_DIR/data/runtime/stack_health.json"

phase "Final notebook-ready state"
docker compose ps

HOST_PORT="$(docker compose port agent 8000 2>/dev/null | tail -n 1 | awk -F: '{print $NF}')"
HOST_PORT="${HOST_PORT:-8788}"
mapfile -t FEATURE_SETS < <(find inputs/private -maxdepth 1 -type f -name '*.json' -printf '%f\n' | sort)

echo
echo "Product evidence platform is ready."
echo "Agent API: http://127.0.0.1:${HOST_PORT}"
echo "Health snapshot: $PROJECT_DIR/data/runtime/stack_health.json"
echo "Artifacts: $PROJECT_DIR/data/artifacts/<row_id>/"
echo "Notebook: $PROJECT_DIR/notebooks/01_run_product_evidence.ipynb"
echo "Available FEATURE_SET values:"
for feature_file in "${FEATURE_SETS[@]}"; do
  echo "  - ${feature_file%.json}"
done

echo
echo "Open the notebook, restart its kernel if it was already open, run the health/setup cell, select FEATURE_SET, and run the product cell."
STARTUP_SUCCEEDED=true
