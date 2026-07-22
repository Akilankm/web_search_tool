#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ "${1:-}" == "--install" ]]; then python -m pip install -e '.[dev]'; fi
exec python -m streamlit run apps/product_url_ui.py --server.address 0.0.0.0 --server.port "${PRODUCT_URL_UI_PORT:-8501}"
