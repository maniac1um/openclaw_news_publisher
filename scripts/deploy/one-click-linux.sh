#!/usr/bin/env bash
# One-click bootstrap for Linux (Ubuntu/Debian/Fedora-like).
# It prepares Python env, installs dependencies, and starts the service.
# It does NOT install/configure PostgreSQL.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${OPENCLAW_BIND_HOST:-0.0.0.0}"
PORT="${OPENCLAW_BIND_PORT:-8000}"

echo "==> OpenClaw one-click bootstrap (Linux)"
echo "==> Project root: $ROOT"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: $PYTHON_BIN not found. Please install Python 3.11+." >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git not found. Please install git first." >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "==> Creating .venv"
  "$PYTHON_BIN" -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

echo "==> Installing dependencies"
python -m pip install --upgrade pip
python -m pip install -e .

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "==> Created .env from .env.example"
  else
    cat > .env <<'EOF'
OPENCLAW_OPENCLAW_API_KEY=dev-openclaw-key
OPENCLAW_OPENCLAW_WS_URL=ws://localhost:18789/ws
EOF
    echo "==> Created minimal .env"
  fi
fi

echo "==> Starting server"
bash scripts/local/restart-server.sh

echo
echo "Done. Open:"
echo "  - Home:  http://127.0.0.1:${PORT}/"
echo "  - Docs:  http://127.0.0.1:${PORT}/docs"
echo "  - Health:http://127.0.0.1:${PORT}/healthz"
echo
echo "Note: PostgreSQL is not auto-installed/configured by this script."
