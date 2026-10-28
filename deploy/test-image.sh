#!/usr/bin/env bash
# Test a built UltraHOFs image the way users get it:
#   1) default container start  -> full smoke test, including a MACE-OFF24 relaxation job
#   2) GitHub Codespaces lifecycle (container kept alive by the platform, service started by
#      the devcontainer's postStartCommand) -> smoke test without relaxation
# Usage: deploy/test-image.sh IMAGE [PORT]        (DOCKER=podman-hpc on NERSC)
set -euo pipefail
IMAGE=$1
PORT=${2:-8000}
DOCKER=${DOCKER:-docker}
HERE=$(cd "$(dirname "$0")" && pwd)

wait_up() {
  for _ in $(seq 1 150); do
    curl -fsS "http://127.0.0.1:$PORT/api/v1/health" >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

echo "== 1) default container start"
cid=$($DOCKER run -d -p "127.0.0.1:$PORT:8000" -e ULTRAHOFS_DEMO_MODE=true "$IMAGE")
trap '$DOCKER logs "$cid" 2>&1 | tail -n 40; $DOCKER rm -f "$cid" >/dev/null 2>&1 || true' EXIT
wait_up || { echo "server did not start"; exit 1; }
python3 "$HERE/smoke_test.py" "http://127.0.0.1:$PORT"
logs=$($DOCKER logs "$cid" 2>&1)
grep -q "seed: loaded" <<<"$logs" || { echo "bundled data were not loaded"; exit 1; }
$DOCKER rm -f "$cid" >/dev/null
trap - EXIT

echo "== 2) Codespaces lifecycle (postStartCommand: ultrahofs-codespaces-start)"
cid=$($DOCKER run -d -p "127.0.0.1:$PORT:8000" -e ULTRAHOFS_DEMO_MODE=true --entrypoint sleep "$IMAGE" infinity)
trap '$DOCKER rm -f "$cid" >/dev/null 2>&1 || true' EXIT
$DOCKER exec "$cid" ultrahofs-codespaces-start
python3 "$HERE/smoke_test.py" "http://127.0.0.1:$PORT" --no-relax
again=$($DOCKER exec "$cid" ultrahofs-codespaces-start)
grep -q "already running" <<<"$again" || { echo "second start did not detect the running service"; exit 1; }
echo "image test passed"
