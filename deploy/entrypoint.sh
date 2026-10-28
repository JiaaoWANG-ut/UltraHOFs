#!/usr/bin/env bash
# UltraHOFs container entry point.
#   all     first-run setup, then job worker + API/web UI on $PORT (default 8000)   [default]
#   api     first-run setup, then API/web UI only (run the worker in another container)
#   worker  job worker only
#   other   executed as a command
set -euo pipefail

# at most 8 threads by default: nproc reports every core of a large shared host (e.g. an HPC login node)
ncpu=$(nproc)
: "${OMP_NUM_THREADS:=$(( ncpu < 8 ? ncpu : 8 ))}"
: "${ULTRAHOFS_TORCH_THREADS:=$OMP_NUM_THREADS}"
export OMP_NUM_THREADS ULTRAHOFS_TORCH_THREADS
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
mkdir -p "${ULTRAHOFS_VAR_DIR:-/data/var}"

case "${1:-all}" in
  all)
    ultrahofs init-db
    ultrahofs worker &
    worker=$!
    uvicorn ultrahofs.main:app --host "$HOST" --port "$PORT" --log-level info &
    web=$!
    trap 'kill -TERM "$web" "$worker" 2>/dev/null || true' TERM INT
    status=0
    wait -n "$web" "$worker" || status=$?
    kill -TERM "$web" "$worker" 2>/dev/null || true
    wait || true
    exit "$status"
    ;;
  api)
    ultrahofs init-db
    exec uvicorn ultrahofs.main:app --host "$HOST" --port "$PORT" --log-level info
    ;;
  worker)
    exec ultrahofs worker
    ;;
  *)
    exec "$@"
    ;;
esac
