#!/usr/bin/env bash
# ============================================================
#  NSE Stock Prediction — single-command launcher (Linux/Mac)
#  Starts the FastAPI backend and the Astro frontend together,
#  streams both logs to this terminal, and cleans up on exit.
#
#  Expected layout (edit BACKEND_DIR / FRONTEND_DIR below if
#  yours differs):
#
#    project-root/
#      backend/            <- server.py, services.py, requirements.txt
#      frontend/           <- this folder (package.json, src/, ...)
#      start.sh            <- this script (run from project-root)
# ============================================================
set -euo pipefail

BACKEND_DIR="backend"
FRONTEND_DIR="frontend"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-4321}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo
echo "=== NSE Stock Prediction — starting backend + frontend ==="
echo

if [ ! -f "$BACKEND_DIR/server.py" ]; then
  echo "[ERROR] Could not find $BACKEND_DIR/server.py"
  echo "        Edit BACKEND_DIR at the top of start.sh to point at your backend folder."
  exit 1
fi

if [ ! -f "$FRONTEND_DIR/package.json" ]; then
  echo "[ERROR] Could not find $FRONTEND_DIR/package.json"
  echo "        Edit FRONTEND_DIR at the top of start.sh to point at this frontend folder."
  exit 1
fi

PIDS=()
cleanup() {
  echo
  echo "Shutting down..."
  for pid in "${PIDS[@]:-}"; do
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# --- Backend: create venv on first run, install deps, launch uvicorn -------
(
  cd "$BACKEND_DIR"
  PYTHON_BIN="python3"
  command -v python3 >/dev/null 2>&1 || PYTHON_BIN="python"

  if [ ! -x ".venv/bin/python" ]; then
    echo "[backend] Creating virtual environment..."
    "$PYTHON_BIN" -m venv .venv
  fi

  echo "[backend] Installing/checking Python dependencies..."
  ./.venv/bin/python -m pip install --quiet --upgrade pip
  if [ -f "requirements.txt" ]; then
    ./.venv/bin/python -m pip install --quiet -r requirements.txt
  else
    echo "[backend] WARNING: requirements.txt not found — skipping dependency install."
  fi

  echo "[backend] Launching FastAPI on http://localhost:${BACKEND_PORT} ..."
  exec ./.venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port "${BACKEND_PORT}"
) 2>&1 | sed -u 's/^/[backend] /' &
PIDS+=("$!")

# --- Frontend: install deps, launch Astro dev server ------------------------
(
  cd "$FRONTEND_DIR"
  if [ ! -d "node_modules" ]; then
    echo "[frontend] Installing npm dependencies (first run only)..."
    npm install
  fi
  echo "[frontend] Launching Astro dev server on http://localhost:${FRONTEND_PORT} ..."
  exec npm run dev -- --port "${FRONTEND_PORT}"
) 2>&1 | sed -u 's/^/[frontend] /' &
PIDS+=("$!")

echo
echo "=== Both servers starting ==="
echo "  Backend:  http://localhost:${BACKEND_PORT}/docs"
echo "  Frontend: http://localhost:${FRONTEND_PORT}"
echo
echo "Press Ctrl+C to stop both."
echo

wait
