#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

pids=()

cleanup() {
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

source .venv/bin/activate
uvicorn main:app --app-dir api --reload --port 8000 &
pids+=("$!")
# exec replaces this subshell with npm itself, so $! below is npm's real
# PID (and killing it cascades to its vite child) instead of an orphaned
# intermediate shell that `cd ... &&` would otherwise leave behind.
(cd web && exec npm run dev) &
pids+=("$!")
wait
