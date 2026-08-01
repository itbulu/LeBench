#!/usr/bin/env bash
# Start LZY Bench Platform (API + Dashboard)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

HOST="${LZY_PLATFORM_HOST:-0.0.0.0}"
PORT="${LZY_PLATFORM_PORT:-8787}"

if [[ ! -d .venv ]]; then
  echo "[INFO] 创建虚拟环境 .venv ..."
  python3 -m venv .venv 2>/dev/null || python -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate

pip install -q -r requirements.txt
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export LZY_PLATFORM_DB="${LZY_PLATFORM_DB:-${ROOT}/data/lzy_bench.db}"

echo "[OK] Dashboard: http://127.0.0.1:${PORT}/"
echo "[OK] OpenAPI:   http://127.0.0.1:${PORT}/docs"
exec uvicorn app.main:app --host "${HOST}" --port "${PORT}"
