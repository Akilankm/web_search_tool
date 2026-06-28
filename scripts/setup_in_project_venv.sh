#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if ! command -v pdm >/dev/null 2>&1; then
  echo "PDM is not installed or not on PATH. Install it first:"
  echo "  python -m pip install --user pdm"
  exit 1
fi

echo "Project root: $PROJECT_ROOT"
echo "Configuring PDM to use an in-project virtual environment at .venv/"
pdm config --local python.use_venv true
pdm config --local venv.in_project true
pdm config --local venv.with_pip true
pdm config --local venv.prompt 'product-evidence-harness-py{python_version}'

echo "Installing runtime + notebook + dev dependencies into .venv/"
pdm install -G notebook -G dev

echo "Ensuring pip is available inside .venv/ for emergency/manual installs"
pdm run python -m ensurepip --upgrade >/dev/null 2>&1 || true

echo "Registering Jupyter kernel"
pdm run python scripts/register_notebook_kernel.py

echo "Validating imports/tests"
pdm run python -m compileall -q src main.py batch_main.py
pdm run pytest -q

echo ""
echo "Done. Use one of:"
echo "  pdm run python main.py --help"
echo "  pdm run python batch_main.py --help"
echo "  eval \$(pdm venv activate)   # optional shell activation"
echo "Notebook kernel: Product Evidence Harness (.venv)"
