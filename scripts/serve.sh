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
  # Alert delivery is configured per deployment. Everything is optional; an
  # unconfigured channel records a skip instead of breaking the pipeline.
  export SMTP_HOST="${SMTP_HOST:-}"
  export SMTP_PORT="${SMTP_PORT:-587}"
  export SMTP_USERNAME="${SMTP_USERNAME:-}"
  export SMTP_PASSWORD="${SMTP_PASSWORD:-}"
  export SMTP_FROM="${SMTP_FROM:-pharma-intel@example.com}"
  export SMTP_USE_TLS="${SMTP_USE_TLS:-true}"
  export ALERT_EMAIL_RECIPIENTS="${ALERT_EMAIL_RECIPIENTS:-}"
  export TEAMS_WEBHOOK_URL="${TEAMS_WEBHOOK_URL:-}"
  export SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
  export SCHEDULER_INTERVAL_MINUTES="${SCHEDULER_INTERVAL_MINUTES:-360}"
  # Prefer the project venv (created with `uv venv .venv`); fall back to a
  # system python that has the requirements installed.
  local py="python3"
  [ -x "$ROOT/backend/.venv/bin/python" ] && py="$ROOT/backend/.venv/bin/python"
  exec "$py" -m uvicorn app.main:app --host 0.0.0.0 --port "$API_PORT"
}

run_web() {
  cd "$ROOT/frontend" || exit 1
  # NEXT_PUBLIC_API_BASE_URL is baked into the client bundle by `npm run build`;
  # exporting it here only affects a build run from this script, not an earlier
  # one. Warn if the existing bundle was built without it, so the browser does
  # not silently fall back to localhost:8000.
  export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-$BE_ORIGIN}"
  if grep -rqs "http://localhost:8000" "$ROOT/frontend/.next/static/chunks" 2>/dev/null; then
    log "WARNING: frontend bundle was built with the localhost:8000 API fallback."
    log "Rebuild: cd frontend && NEXT_PUBLIC_API_BASE_URL=$BE_ORIGIN npm run build"
  fi
  # This build uses output: standalone, so serve it with the standalone server
  # (next start does not support standalone and exits).
  local dir="$ROOT/frontend/.next/standalone"
  mkdir -p "$dir/.next"
  # Always refresh: a rebuild leaves stale chunks in the standalone dir, which
  # the server would otherwise keep serving (its manifest points at new hashes).
  rm -rf "$dir/.next/static" "$dir/public"
  cp -r "$ROOT/frontend/.next/static" "$dir/.next/static"
  cp -r "$ROOT/frontend/public" "$dir/public"
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
