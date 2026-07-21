#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PORT="${STREAMLIT_PORT:-8501}"
ADDRESS="${STREAMLIT_ADDRESS:-0.0.0.0}"
INSTALL_DEPS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install)
      INSTALL_DEPS=true
      shift
      ;;
    --port)
      PORT="${2:?--port requires a value}"
      shift 2
      ;;
    --address)
      ADDRESS="${2:?--address requires a value}"
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Usage: ./scripts/run_product_evidence_ui.sh [--install] [--port 8501] [--address 0.0.0.0]

Starts the Product Evidence Platform user interface against the local agent API.
Use --install once in a new Azure ML VS Code environment to install the UI
requirements from requirements/ui.txt.
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "${INSTALL_DEPS}" == "true" ]]; then
  python -m pip install -r requirements/ui.txt
fi

if ! python - <<'PY' >/dev/null 2>&1
import streamlit
PY
then
  echo "Streamlit is not installed in the current Python environment." >&2
  echo "Run: ./scripts/run_product_evidence_ui.sh --install" >&2
  exit 1
fi

export PYTHONPATH="${ROOT_DIR}:${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"
export PRODUCT_AGENT_URL="${PRODUCT_AGENT_URL:-http://127.0.0.1:${AGENT_HOST_PORT:-8788}}"

cat <<EOF
Product Evidence Platform UI starting
  UI address : http://${ADDRESS}:${PORT}
  Agent API  : ${PRODUCT_AGENT_URL}
  Repository : ${ROOT_DIR}

In Azure ML VS Code, open the Ports panel and forward port ${PORT} privately.
EOF

exec python -m streamlit run apps/product_evidence_ui.py \
  --server.address "${ADDRESS}" \
  --server.port "${PORT}" \
  --server.headless true \
  --browser.gatherUsageStats false
