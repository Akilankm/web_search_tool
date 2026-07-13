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

mkdir -p artifacts inputs/private secrets
if [[ ! -s secrets/browser_api_token.txt ]]; then
  python - <<'PY'
from pathlib import Path
import secrets
path = Path("secrets/browser_api_token.txt")
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

# Bind-mounted folders must be writable by the same Azure ML user that owns the
# checkout. When this script is launched by a root startup hook, use the checkout
# owner's UID/GID rather than running the application containers as root.
export RUNTIME_UID="${PRODUCT_EVIDENCE_RUNTIME_UID:-$(stat -c '%u' "$PROJECT_DIR")}" 
export RUNTIME_GID="${PRODUCT_EVIDENCE_RUNTIME_GID:-$(stat -c '%g' "$PROJECT_DIR")}" 

if [[ "$RUNTIME_UID" == "0" ]]; then
  echo "Refusing to run application containers as root. Set PRODUCT_EVIDENCE_RUNTIME_UID/GID to the Azure ML notebook user." >&2
  exit 1
fi

docker compose up -d --build --remove-orphans

if ! python scripts/wait_for_stack.py; then
  docker compose ps >&2 || true
  docker compose logs --tail=200 agent browser >&2 || true
  exit 1
fi

echo "Product evidence platform is ready at http://127.0.0.1:${AGENT_HOST_PORT:-8788}"
echo "Open notebooks/01_run_product_evidence.ipynb in Azure ML Studio."
