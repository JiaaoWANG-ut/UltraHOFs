#!/usr/bin/env bash
# UltraHOFs development launcher (NERSC login node friendly).
#
#   scripts/dev.sh           # API (127.0.0.1:8000) + job worker + Vite dev server (127.0.0.1:5173)
#   scripts/dev.sh prod      # API serving the built UI on 127.0.0.1:8000 + job worker
#
# All services bind to 127.0.0.1 only (login nodes are shared). Open the UI from your laptop via
# VS Code Remote-SSH port forwarding (Ports panel) or:  ssh -L 5173:127.0.0.1:5173 <user>@perlmutter.nersc.gov
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_PREFIX="${ULTRAHOFS_ENV:-/global/cfs/cdirs/m4517/jiaao/envs/ultrahofs}"
export PATH="$ENV_PREFIX/bin:$PATH"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"
MODE="${1:-dev}"
LOGDIR="$ROOT/var/logs"
mkdir -p "$LOGDIR"

pids=()
cleanup() {
  echo "stopping UltraHOFs services…"
  for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "$ROOT"
python -m ultrahofs.cli init-db

python -m uvicorn ultrahofs.main:app --host 127.0.0.1 --port "${API_PORT:-8000}" \
  $([[ "$MODE" == "dev" ]] && echo "--reload --reload-dir backend/ultrahofs") >"$LOGDIR/api.log" 2>&1 &
pids+=($!)
echo "API      → http://127.0.0.1:${API_PORT:-8000}/api/docs   (log: var/logs/api.log)"

python -m ultrahofs.cli worker >"$LOGDIR/worker.log" 2>&1 &
pids+=($!)
echo "worker   → var/logs/worker.log"

if [[ "$MODE" == "dev" ]]; then
  (cd frontend && npm run dev) >"$LOGDIR/web.log" 2>&1 &
  pids+=($!)
  echo "web (dev) → http://127.0.0.1:5173   (log: var/logs/web.log)"
else
  [[ -d frontend/dist ]] || (cd frontend && npm run build)
  echo "web (built UI) → http://127.0.0.1:${API_PORT:-8000}"
fi

echo "press Ctrl-C to stop"
wait
