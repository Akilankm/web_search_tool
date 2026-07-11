#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PRODUCT_EVIDENCE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$PROJECT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed on this Azure ML Compute Instance." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon access is unavailable. Enable root/Docker permissions or run this as an Azure ML startup script." >&2
  exit 1
fi

mkdir -p artifacts inputs/private secrets
if [[ ! -s secrets/browser_api_token.txt ]]; then
  python - <<'PY'
from pathlib import Path
import secrets
path = Path('secrets/browser_api_token.txt')
path.write_text(secrets.token_urlsafe(48), encoding='utf-8')
path.chmod(0o600)
PY
fi

docker compose up -d --build --remove-orphans
python scripts/wait_for_stack.py

echo "Product evidence platform is ready at http://127.0.0.1:${AGENT_HOST_PORT:-8788}"
