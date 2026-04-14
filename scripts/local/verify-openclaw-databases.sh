#!/usr/bin/env bash
# 校验 .env 中三条 PostgreSQL DSN 是否可用，以及关键表是否存在。
# 用法：在仓库根目录执行  bash scripts/local/verify-openclaw-databases.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "未找到 $ROOT/.env，请先配置 OPENCLAW_DATABASE_URL 等变量。" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

check_url() {
  local name="$1" url="$2" expect_table="$3"
  if [[ -z "${url}" ]]; then
    echo "[${name}] 跳过：未设置 URL"
    return 0
  fi
  # 仅打印 host/db，避免把密码打到终端
  local safe="${url#*@}"
  echo "[${name}] 连接 …@${safe}"
  psql "$url" -v ON_ERROR_STOP=1 -tAc "SELECT 1" >/dev/null
  if [[ -n "${expect_table}" ]]; then
    local n
    n="$(psql "$url" -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = '${expect_table}';")"
    if [[ "${n}" != "1" ]]; then
      echo "[${name}] 失败：缺少表 ${expect_table}" >&2
      exit 1
    fi
    echo "[${name}] 表 ${expect_table} 存在"
  else
    echo "[${name}] 连接成功"
  fi
}

check_url "主库(报告)" "${OPENCLAW_DATABASE_URL:-}" "reports"
check_url "监测库" "${OPENCLAW_MONITORING_DATABASE_URL:-}" "price_monitors"
check_url "新闻库" "${OPENCLAW_NEWS_DATABASE_URL:-}" "news_library"

echo "全部检查通过。"
