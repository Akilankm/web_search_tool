#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PRODUCT_EVIDENCE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$PROJECT_DIR"

python scripts/preflight_azureml.py --project-dir "$PROJECT_DIR"

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
