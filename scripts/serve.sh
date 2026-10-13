#!/usr/bin/env bash
# Local supervisor for the demo deployment.
#
# The sandbox reaps processes attached to an interactive shell session, which
# left the frontend as a zombie and the public URL showing 502. This script
# restarts either service if it exits, and is itself launched with setsid so it
# survives the shell that started it.
#
# Usage: setsid bash scripts/serve.sh >/tmp/serve.log 2>&1 &

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PORT=12001
WEB_PORT=12000
FE_ORIGIN="https://work-1-hoqpnvjomogubgav.prod-runtime.all-hands.dev"
BE_ORIGIN="https://work-2-hoqpnvjomogubgav.prod-runtime.all-hands.dev"

log() { echo "[serve $(date +%H:%M:%S)] $*"; }

run_api() {
  cd "$ROOT/backend" || exit 1
  export ENVIRONMENT=development
  export JWT_SECRET="${JWT_SECRET:-demo-secret-please-replace}"
  export CORS_ORIGINS="[\"$FE_ORIGIN\",\"$BE_ORIGIN\",\"http://localhost:$WEB_PORT\"]"
  exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "$API_PORT"
}

run_web() {
  cd "$ROOT/frontend" || exit 1
  # This build uses output: standalone, so serve it with the standalone server
  # (next start does not support standalone and exits).
  local dir="$ROOT/frontend/.next/standalone"
  mkdir -p "$dir/.next"
  [ -d "$dir/.next/static" ] || cp -r "$ROOT/frontend/.next/static" "$dir/.next/static"
  [ -d "$dir/public" ] || cp -r "$ROOT/frontend/public" "$dir/public"
  cd "$dir" || exit 1
  PORT="$WEB_PORT" HOSTNAME=0.0.0.0 exec node server.js
}

supervise() {
  local name="$1"; shift
  while true; do
    "$@" >>"/tmp/$name.out" 2>&1 &
    local pid=$!
    log "$name started (pid $pid)"
    wait "$pid"
    log "$name exited (code $?), restarting in 3s"
    sleep 3
  done
}

supervise "api" run_api &
supervise "web" run_web &
wait
