#!/usr/bin/env bash
# Start OpenClaw News Publisher locally (Linux/macOS).
# Safe to commit: no machine-specific paths or secrets.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PIDFILE="${TMPDIR:-/tmp}/openclaw_news_publisher.uvicorn.pid"
LOG="${TMPDIR:-/tmp}/openclaw_news_publisher.server.log"
HOST="${OPENCLAW_BIND_HOST:-0.0.0.0}"
PORT="${OPENCLAW_BIND_PORT:-8000}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
AUTO_SETUP="${OPENCLAW_AUTO_SETUP:-1}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: python3 is required. Please install Python 3.11+." >&2
  exit 1
fi

if curl -sS -o /dev/null --connect-timeout 1 "http://127.0.0.1:${PORT}/healthz" 2>/dev/null; then
  echo "Server is already running: http://127.0.0.1:${PORT}/healthz"
  exit 0
fi

if [[ ! -d .venv ]]; then
  if [[ "$AUTO_SETUP" != "1" ]]; then
    echo "ERROR: .venv not found. Run setup first, or set OPENCLAW_AUTO_SETUP=1." >&2
    exit 1
  fi
  echo "[setup] Creating virtual environment..."
  "$PYTHON_BIN" -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

if [[ "$AUTO_SETUP" == "1" ]]; then
  echo "[setup] Installing/updating dependencies..."
  python -m pip install --upgrade pip >/dev/null
  python -m pip install -e . >/dev/null
fi

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
  fi
  echo "WARN: .env not found. Create .env before using database-backed features."
fi

nohup python -m uvicorn app.main:app --host "$HOST" --port "$PORT" --reload >>"$LOG" 2>&1 &
echo $! >"$PIDFILE"
echo "Started (pid file: $PIDFILE, log: $LOG)"
sleep 2

if curl -sS -o /dev/null --connect-timeout 2 "http://127.0.0.1:${PORT}/healthz"; then
  echo "Health check OK: http://127.0.0.1:${PORT}/healthz"
else
  echo "WARN: Health check failed. Inspect logs: tail -50 $LOG" >&2
  exit 1
fi

if [[ "${OPENCLAW_WORKFLOW_POST_CHECK:-1}" == "1" ]]; then
  # shellcheck source=/dev/null
  source "$ROOT/scripts/local/workflow-post-check.sh"
  workflow_post_check "$PORT" || true
fi
