#!/usr/bin/env bash
# Stop local OpenClaw News Publisher uvicorn processes.
# Safe to commit: no machine-specific paths or secrets.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PIDFILE="${TMPDIR:-/tmp}/openclaw_news_publisher.uvicorn.pid"
PORT="${OPENCLAW_BIND_PORT:-8000}"

# 优先按 PID 文件结束 nohup 启动的父进程（reloader）
if [[ -f "$PIDFILE" ]]; then
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    sleep 1
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$PIDFILE"
fi

# 兜底：按命令行匹配本项目（避免误杀其他目录下的 uvicorn）
pkill -f "uvicorn app.main:app.*--port ${PORT}" 2>/dev/null || true
pkill -f "uvicorn app.main:app" 2>/dev/null || true

if curl -sS -o /dev/null --connect-timeout 1 "http://127.0.0.1:${PORT}/healthz" 2>/dev/null; then
  echo "Port ${PORT} still responds. Please inspect manually: ss -tlnp | grep ${PORT}"
else
  echo "Stopped (or no running process found)."
fi
