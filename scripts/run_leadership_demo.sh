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
Usage: ./scripts/run_leadership_demo.sh [--install] [--port 8501] [--address 0.0.0.0]

Starts the leadership Streamlit UI against the local Product Evidence Agent.
Use --install once in a fresh Azure ML VS Code environment to install the small
host-side demo dependency set from requirements/demo.txt.
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
  python -m pip install -r requirements/demo.txt
fi

if ! python - <<'PY' >/dev/null 2>&1
import streamlit
PY
then
  echo "Streamlit is not installed in the current Azure ML VS Code Python environment." >&2
  echo "Run: ./scripts/run_leadership_demo.sh --install" >&2
  exit 1
fi

export PYTHONPATH="${ROOT_DIR}:${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"
export PRODUCT_AGENT_URL="${PRODUCT_AGENT_URL:-http://127.0.0.1:${AGENT_HOST_PORT:-8788}}"

cat <<EOF
Leadership demo starting
  UI address : http://${ADDRESS}:${PORT}
  Agent API  : ${PRODUCT_AGENT_URL}
  Repository : ${ROOT_DIR}

In Azure ML VS Code, open the Ports panel and forward port ${PORT}.
EOF

exec python -m streamlit run apps/leadership_demo.py \
  --server.address "${ADDRESS}" \
  --server.port "${PORT}" \
  --server.headless true \
  --browser.gatherUsageStats false
