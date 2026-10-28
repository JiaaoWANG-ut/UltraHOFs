#!/usr/bin/env bash
# GitHub Codespaces (postStartCommand): start UltraHOFs in the background and wait until it answers.
set -uo pipefail
URL="http://127.0.0.1:${PORT:-8000}/api/v1/health"
LOG="${ULTRAHOFS_VAR_DIR:-/data/var}/logs/server.log"
mkdir -p "$(dirname "$LOG")"
if curl -fsS "$URL" >/dev/null 2>&1; then
  echo "UltraHOFs is already running on port ${PORT:-8000}"
  exit 0
fi
setsid nohup ultrahofs-entrypoint all >"$LOG" 2>&1 </dev/null &
for _ in $(seq 1 180); do
  if curl -fsS "$URL" >/dev/null 2>&1; then
    echo "UltraHOFs is ready on port ${PORT:-8000} (log: $LOG)"
    exit 0
  fi
  sleep 1
done
echo "UltraHOFs did not start within 180 s; last log lines:"
tail -n 40 "$LOG"
exit 1
