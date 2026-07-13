#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PRODUCT_EVIDENCE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ALLOW_INSECURE_ENV_PERMISSIONS=false

usage() {
  cat <<'EOF'
Usage: ./scripts/azureml_startup.sh [--allow-insecure-env-permissions]

Options:
  --allow-insecure-env-permissions
      Permit broad .env modes such as 777 when an Azure ML mounted filesystem
      cannot preserve mode 600. This weakens credential protection and emits a
      security warning.
  -h, --help
      Show this help message.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --allow-insecure-env-permissions)
      ALLOW_INSECURE_ENV_PERMISSIONS=true
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

case "${PRODUCT_EVIDENCE_ALLOW_INSECURE_ENV_PERMISSIONS:-false}" in
  1|true|TRUE|yes|YES|on|ON)
    ALLOW_INSECURE_ENV_PERMISSIONS=true
    ;;
esac

cd "$PROJECT_DIR"

# A fresh clone contains no generated runtime folders. Create the complete
# repository-local runtime layout before preflight or Docker Compose runs.
mkdir -p data/artifacts data/runtime inputs/private secrets

if [[ ! -s secrets/browser_api_token.txt ]]; then
  python - <<'PY'
from pathlib import Path
import secrets

path = Path("secrets/browser_api_token.txt")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
path.chmod(0o600)
PY
fi

preflight_args=(--project-dir "$PROJECT_DIR")
if [[ "$ALLOW_INSECURE_ENV_PERMISSIONS" == "true" ]]; then
  echo "SECURITY WARNING: allowing broad .env permissions for this startup." >&2
  preflight_args+=(--allow-insecure-env-permissions)
fi
python scripts/preflight_azureml.py "${preflight_args[@]}"

# Prefer the identity of the user invoking startup. Azure ML cloudfiles mounts
# can report the checkout owner as root even when the notebook user is the
# correct non-root runtime identity.
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

docker compose up -d --build --remove-orphans

if ! python scripts/wait_for_stack.py; then
  docker compose ps >&2 || true
  docker compose logs --tail=200 agent browser >&2 || true
  exit 1
fi

echo "Product evidence platform is ready at http://127.0.0.1:${AGENT_HOST_PORT:-8788}"
echo "Artifacts will be written under $PROJECT_DIR/data/artifacts/<row_id>/"
echo "Open notebooks/01_run_product_evidence.ipynb in Azure ML Studio."
