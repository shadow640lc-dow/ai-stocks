#!/usr/bin/env bash
# AI Hedge Fund web application launcher (Linux / macOS).
# Mirrors app/run.bat: installs dependencies, starts the FastAPI backend and
# the Vite dev server, then opens the browser.
set -euo pipefail

APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
ROOT_DIR="$(cd "$APP_DIR/.." && pwd)"
cd "$ROOT_DIR"

info() { printf '\033[36m[INFO]\033[0m %s\n' "$*"; }
success() { printf '\033[32m[SUCCESS]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[WARNING]\033[0m %s\n' "$*"; }
fail() { printf '\033[31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

for cmd in node npm python3 poetry; do
  command -v "$cmd" >/dev/null 2>&1 || fail "$cmd is not installed. See app/README.md for prerequisites."
done

if [ ! -f "$ROOT_DIR/.env" ]; then
  if [ -f "$ROOT_DIR/.env.example" ]; then
    warn "No .env file found. Creating one from .env.example..."
    cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
    warn "Edit .env and add your API keys before running live features."
  else
    fail "No .env or .env.example found in $ROOT_DIR."
  fi
else
  success "Environment file (.env)"
fi

info "Checking backend dependencies..."
if ! poetry run python -c "import uvicorn, fastapi" >/dev/null 2>&1; then
  info "Installing Python dependencies with Poetry..."
  poetry install
fi

info "Checking frontend dependencies..."
if [ ! -d "$APP_DIR/frontend/node_modules" ]; then
  info "Installing Node.js dependencies..."
  (cd "$APP_DIR/frontend" && npm install)
fi

BACKEND_PID=""
FRONTEND_PID=""
cleanup() {
  trap - EXIT INT TERM
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
  pkill -P "$BACKEND_PID" 2>/dev/null || true
  exit 0
}
trap cleanup EXIT INT TERM

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

info "Starting backend server on port $BACKEND_PORT..."
poetry run uvicorn app.backend.main:app --reload --host 127.0.0.1 --port "$BACKEND_PORT" &
BACKEND_PID=$!

for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:$BACKEND_PORT/" >/dev/null 2>&1; then break; fi
  sleep 1
done

info "Starting frontend dev server on port $FRONTEND_PORT..."
(cd "$APP_DIR/frontend" && npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort) &
FRONTEND_PID=$!

sleep 3
info "Opening browser..."
python3 -m webbrowser "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1 || true

cat <<EOF

AI Hedge Fund web application is running:
  Frontend: http://localhost:$FRONTEND_PORT
  Backend:  http://127.0.0.1:$BACKEND_PORT
  Docs:     http://127.0.0.1:$BACKEND_PORT/docs

Press Ctrl+C to stop both services.
EOF

wait
