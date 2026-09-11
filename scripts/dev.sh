#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
BACKEND_PID=""
FRONTEND_PID=""

usage() {
  echo "Start the Invoice Review backend and frontend in one terminal."
  echo
  echo "Usage: ./scripts/dev.sh [--check|--help]"
  echo
  echo "  --check  Verify the existing local environment without starting services."
  echo "  --help   Show this help message."
  echo
  echo "This command does not install or update dependencies."
}

fail() {
  echo "Error: $1" >&2
  exit 1
}

port_is_listening() {
  local port="$1"

  if command -v ss >/dev/null 2>&1; then
    ss -H -ltn | awk -v suffix=":$port" '$4 ~ (suffix "$") { found = 1 } END { exit !found }'
    return
  fi

  lsof -nP -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1
}

check_local_environment() {
  command -v uv >/dev/null 2>&1 || fail "uv is required. Install uv, then run the documented setup commands."
  command -v pnpm >/dev/null 2>&1 || fail "pnpm is required. Install pnpm, then run the documented setup commands."
  [[ -d "$BACKEND_DIR/.venv" ]] || fail "backend/.venv is missing. Run 'cd backend && uv sync --locked'."
  [[ -d "$FRONTEND_DIR/node_modules" ]] || fail "frontend/node_modules is missing. Run 'cd frontend && pnpm install --frozen-lockfile'."
  [[ -f "$BACKEND_DIR/uv.lock" ]] || fail "backend/uv.lock is missing."
  [[ -f "$FRONTEND_DIR/pnpm-lock.yaml" ]] || fail "frontend/pnpm-lock.yaml is missing."
  if port_is_listening 8000; then
    fail "port 8000 is already in use. Stop the existing API before starting."
  fi
  if port_is_listening 5173; then
    fail "port 5173 is already in use. Stop the existing UI before starting."
  fi
}

cleanup() {
  local process_id

  trap - EXIT INT TERM
  for process_id in "$BACKEND_PID" "$FRONTEND_PID"; do
    if [[ -n "$process_id" ]] && kill -0 "$process_id" 2>/dev/null; then
      kill "$process_id" 2>/dev/null || true
    fi
  done
  for process_id in "$BACKEND_PID" "$FRONTEND_PID"; do
    if [[ -n "$process_id" ]]; then
      wait "$process_id" 2>/dev/null || true
    fi
  done
}

case "${1:-}" in
  --help|-h)
    usage
    exit 0
    ;;
  --check)
    check_local_environment
    echo "Invoice Review is ready to start."
    exit 0
    ;;
  "")
    ;;
  *)
    usage >&2
    fail "unknown option: $1"
    ;;
esac

check_local_environment
trap cleanup EXIT
trap 'exit 130' INT TERM

echo "Starting API at http://localhost:8000"
(
  cd "$BACKEND_DIR"
  uv run --locked --no-sync uvicorn app.main:create_app --factory --reload
) &
BACKEND_PID=$!

echo "Starting UI at http://localhost:5173"
cd "$FRONTEND_DIR"
pnpm dev &
FRONTEND_PID=$!
cd "$PROJECT_ROOT"

status=0
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done

if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
  wait "$BACKEND_PID" || status=$?
else
  wait "$FRONTEND_PID" || status=$?
fi

exit "$status"
