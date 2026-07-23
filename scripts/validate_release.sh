#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

python -m compileall -q src scripts
python -m json.tool config/default.json >/dev/null
for file in feature_sets/*.json; do python -m json.tool "$file" >/dev/null; done
bash -n scripts/validate_release.sh

python scripts/check_architecture.py
python scripts/validate_notebooks.py
pytest -q \
  tests/test_acceptance_policy.py \
  tests/test_mandatory_url_delivery.py \
  tests/test_rendered_source_classification.py \
  tests/test_release_consistency.py \
  tests/test_notebook_runtime.py
pytest -q
