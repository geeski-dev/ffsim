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
(cd web && exec npm run dev) &
pids+=("$!")
wait
