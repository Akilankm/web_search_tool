#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
mkdir -p data/artifacts secrets
if [[ ! -f .env ]]; then cp .env.example .env; fi
if [[ ! -s secrets/browser_api_token.txt ]]; then
  python - <<'PY' > secrets/browser_api_token.txt
import secrets
print(secrets.token_urlsafe(32))
PY
fi
if grep -q '^BROWSER_API_TOKEN=change-me$' .env; then
  token="$(cat secrets/browser_api_token.txt)"
  python - "$token" <<'PY'
from pathlib import Path
import sys
path = Path('.env')
text = path.read_text()
text = text.replace('BROWSER_API_TOKEN=change-me', f'BROWSER_API_TOKEN={sys.argv[1]}')
path.write_text(text)
PY
fi
args=(up -d --remove-orphans)
if [[ "${1:-}" == "--build" ]]; then args=(up -d --build --force-recreate --remove-orphans); fi
docker compose "${args[@]}"
docker compose ps
