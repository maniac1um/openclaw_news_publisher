#!/usr/bin/env bash
# 从仓库任意位置调用：一键启动桌面 WebView（实际逻辑在 webview_app/launch.sh）。
# 说明：webview_app 目录默认被 .gitignore 忽略；若你尚未在本地创建该目录，请先按文档准备或从备份恢复。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LAUNCH="$ROOT/webview_app/launch.sh"

if [[ ! -f "$LAUNCH" ]]; then
  echo "ERROR: 未找到 $LAUNCH" >&2
  echo "请在项目根下维护 webview_app 目录（含 launch.sh、main.py、requirements.txt），或从本机备份复制。" >&2
  exit 1
fi

exec bash "$LAUNCH" "$@"
