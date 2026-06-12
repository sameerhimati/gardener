#!/usr/bin/env bash
# Gardener dev runner: backend (uvicorn :8000) + web (next dev :3000) together.
# Ctrl-C kills both. Run from anywhere: scripts/dev.sh
set -eo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Load .env if present (exported so child processes see it)
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  echo "[dev] loaded .env"
fi

PIDS=()
cleanup() {
  echo
  echo "[dev] shutting down..."
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Backend — prefer the project venv's uvicorn if it exists
UVICORN="uvicorn"
if [ -x .venv/bin/uvicorn ]; then
  UVICORN=".venv/bin/uvicorn"
fi
echo "[dev] starting backend on :8000 ($UVICORN)"
"$UVICORN" backend.app:app --reload --port 8000 &
PIDS+=($!)

# Web — tolerate web/ not existing yet (parallel agent may still be creating it)
if [ -d web ] && [ -f web/package.json ]; then
  echo "[dev] starting web on :3000"
  (cd web && npm run dev) &
  PIDS+=($!)
else
  echo "[dev] WARNING: web/ not found (or no package.json) — running backend only"
fi

wait
