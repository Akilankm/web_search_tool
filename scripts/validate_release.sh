#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python -m compileall -q src apps
python -m json.tool config/default.json >/dev/null
for file in feature_sets/*.json; do python -m json.tool "$file" >/dev/null; done
bash -n scripts/start.sh scripts/run_ui.sh scripts/validate_release.sh
docker compose config --quiet
pytest -q
