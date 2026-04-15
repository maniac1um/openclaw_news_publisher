# OpenClaw News Publisher

一个用于接收 OpenClaw 报告、自动处理并发布到网站页面的服务。

## 项目目标

- 接收 OpenClaw 生成的结构化新闻分析 JSON。
- 完成入站校验、幂等处理、落盘与状态跟踪。
- 将报告渲染为前端可读数据并触发 git 发布流程。
- 提供可直接访问的用户页面展示报告。

## 功能概览

- OpenClaw 接入 API（FastAPI）
  - `POST /api/v1/openclaw/reports`
  - `GET /api/v1/openclaw/reports/{ingest_id}`
  - `POST /api/v1/openclaw/reports/{ingest_id}/retry`（预留）
  - 价格监测（默认由 OpenClaw 外采，服务端只入库与查询）
    - `POST /api/v1/openclaw/monitoring/bootstrap`（默认仅建任务 + 占位 URL，不生成大量候选抓取链）
    - `POST /api/v1/openclaw/monitoring/{monitor_id}/observations/ingest`（OpenClaw 上报解析后的价格观测）
    - `GET /api/v1/openclaw/monitoring/{monitor_id}/summary?window_days=7`（需 API Key）
    - `POST /api/v1/openclaw/monitoring/{monitor_id}/urls`（可选，补充参考 URL）
    - `POST /api/v1/openclaw/monitoring/{monitor_id}/run-once`（仅当开启服务端抓取时才会外网拉页；默认跳过）
    - `GET /api/v1/openclaw/monitoring/scheduler/status`
    - `POST /api/v1/openclaw/monitoring/external-heartbeat`（外部 cron/scheduler 心跳上报）
  - 价格监测公开读（供 OpenClaw 定时拉库、前端展示，无需 API Key）
    - `GET /api/v1/public/monitoring/monitors`
    - `GET /api/v1/public/monitoring/{monitor_id}/timeseries`
    - `GET /api/v1/public/monitoring/{monitor_id}/observations`
- OpenClaw 门户聊天（FastAPI WebSocket）
  - 首页聊天框：OpenClaw 回复在左侧气泡、用户消息在右侧气泡实时展示
  - 中转接口：`WS /api/v1/chat/ws`（服务端连接 OpenClaw Gateway，并将流式增量内容按 `200ms` 聚合后推送前端）
  - 会话在浏览器本地持久化（`localStorage`）：刷新/切页可恢复，支持“删除当前会话”和“清空缓存”
  - 当前为单设备本地持久化；多设备同步建议见 `docs/architecture/news-pipeline.md`（对话持久化演进）
- 用户页面与公开查询 API
  - `/`（门户首页：OpenClaw 对话 + 工作情况 + 网页化工作流控制台）
  - `/topic-analysis`（专题分析：开发中）
  - `/price-trend`（价格趋势：开发中）
  - `/keyword-tracking`（关键词追踪：开发中）
  - `GET /api/v1/public/reports`
  - `GET /api/v1/public/reports/{ingest_id}`
  - `POST /api/v1/public/reports/bulk-delete`（批量删除）
  - `GET /api/v1/public/monitoring/scheduler-status`（内部调度器状态）
  - `GET /api/v1/public/monitoring/external-jobs`（外部任务最近心跳）
  - 网页工作流控制台 API
    - `GET /api/v1/public/workflow/state`
    - `POST /api/v1/public/workflow/monitor/bootstrap`
    - `POST /api/v1/public/workflow/analysis/run`
    - `GET /api/v1/public/workflow/external-configs`
    - `POST /api/v1/public/workflow/external-configs`
    - `POST /api/v1/public/workflow/external-configs/{job_name}/toggle`
    - `GET /api/v1/public/workflow/external-runs`
- 文档与运维
  - `/docs`（Swagger）
  - `/healthz`（健康检查）
  - `/healthz/db`（数据库连通性检查；未配置数据库时返回 enabled=false）
- 自动化发布
  - 渲染产物默认写入 `content/reports/rendered/`（运行时目录，不纳入 Git）
  - 发布脚本 `scripts/publish_site.py` 执行 git add/commit（可选 push）

## 目录结构

```text
openclaw_news_publisher/
├─ .gitattributes
├─ app/
│  ├─ api/v1/chat.py
│  ├─ api/v1/openclaw.py
│  ├─ core/
│  │  ├─ config.py
│  │  └─ security.py
│  ├─ db/
│  │  ├─ models.py
│  │  └─ repositories.py
│  ├─ schemas/report.py
│  ├─ services/
│  │  ├─ intake_service.py
│  │  ├─ report_service.py
│  │  ├─ openclaw_chat_bridge.py
│  │  └─ publish_service.py
│  ├─ workers/job_runner.py
│  └─ main.py
├─ docs/
│  ├─ api/openclaw-intake.md（报告入站 + 价格监测 ingest 约定）
│  ├─ architecture/news-pipeline.md
│  └─ cross-platform-development.md
├─ scripts/
│  ├─ deploy/
│  │  ├─ one-click-linux.sh
│  │  └─ one-click-windows.ps1
│  ├─ local/
│  │  ├─ start-server.sh
│  │  ├─ stop-server.sh
│  │  ├─ restart-server.sh
│  │  └─ verify-openclaw-databases.sh
│  └─ publish_site.py
├─ tests/
│  ├─ api/test_openclaw_intake.py
│  └─ services/test_report_pipeline.py
└─ pyproject.toml
```

## 技术栈

- Python 3.11+
- FastAPI
- Pydantic v2
- Pytest
- websockets（用于后端代理 OpenClaw Gateway 流式聊天事件）
- psycopg（用于 PostgreSQL 持久化）

## 一键部署（Linux / Windows）

> 目标：在新设备上快速拉起服务（创建虚拟环境、安装依赖、启动服务）。  
> 说明：**脚本不安装/不配置 PostgreSQL**，仅使用你已有的数据库配置。

### 前置条件（必须）

- 已安装 `git`
- 已安装 Python 3.11+
- 可访问 PyPI（用于安装 Python 依赖）
- （可选但推荐）已准备 PostgreSQL，并具备对应库连接串  
  - `OPENCLAW_DATABASE_URL`
  - `OPENCLAW_MONITORING_DATABASE_URL`
  - `OPENCLAW_NEWS_DATABASE_URL`

### 先部署 PostgreSQL（推荐）

> 如果你需要报告/新闻库/价格监测持久化，请先完成本节，再执行 one-click 脚本。

#### Linux（Ubuntu/Debian）示例

1) 安装并启动 PostgreSQL

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql
```

2) 创建 3 个角色与 3 个数据库（主库/监测库/新闻库）

```bash
sudo -u postgres psql <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'openclaw_app') THEN
    CREATE ROLE openclaw_app LOGIN PASSWORD 'REPLACE_ME_APP';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'openclaw_monitor') THEN
    CREATE ROLE openclaw_monitor LOGIN PASSWORD 'REPLACE_ME_MONITOR';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'openclaw_news') THEN
    CREATE ROLE openclaw_news LOGIN PASSWORD 'REPLACE_ME_NEWS';
  END IF;
END$$;
SQL

sudo -u postgres psql -c "CREATE DATABASE openclaw_app OWNER openclaw_app;"
sudo -u postgres psql -c "CREATE DATABASE openclaw_monitor OWNER openclaw_monitor;"
sudo -u postgres psql -c "CREATE DATABASE openclaw_news OWNER openclaw_news;"
```

3) 填写 `.env` 连接串（示例）

```env
OPENCLAW_DATABASE_URL=postgresql://openclaw_app:REPLACE_ME_APP@127.0.0.1:5432/openclaw_app
OPENCLAW_MONITORING_DATABASE_URL=postgresql://openclaw_monitor:REPLACE_ME_MONITOR@127.0.0.1:5432/openclaw_monitor
OPENCLAW_NEWS_DATABASE_URL=postgresql://openclaw_news:REPLACE_ME_NEWS@127.0.0.1:5432/openclaw_news
```

4) 验证数据库连通性（项目根目录）

```bash
bash scripts/local/verify-openclaw-databases.sh
```

#### Windows 示例（Docker Desktop）

如果你的 Windows 本机未安装 PostgreSQL，建议先用 Docker 拉起：

```powershell
docker run --name openclaw-postgres `
  -e POSTGRES_PASSWORD=postgres `
  -p 5432:5432 `
  -d postgres:16
```

然后进入容器执行与 Linux 相同的建角色/建库 SQL（或用 psql 客户端连接后执行），最后按上面的 `.env` 示例填写连接串。

### Linux 一键部署

```bash
git clone https://github.com/maniac1um/openclaw_news_publisher.git
cd openclaw_news_publisher
bash scripts/deploy/one-click-linux.sh
```

### Windows 一键部署（PowerShell）

```powershell
git clone https://github.com/maniac1um/openclaw_news_publisher.git
cd openclaw_news_publisher
powershell -ExecutionPolicy Bypass -File .\scripts\deploy\one-click-windows.ps1
```

脚本默认行为：

- 自动创建 `.venv`（若不存在）
- 自动执行 `pip install -e .`
- 若 `.env` 不存在，则从 `.env.example` 复制
- 自动启动 `uvicorn app.main:app`

> 若你还未配置 PostgreSQL，可先用最小 `.env` 启动服务；数据库相关功能会按接口返回提示（例如 503 或 enabled=false）。

## 快速开始（本地）

以下示例基于 **Ubuntu 24.04 LTS**，并以 PostgreSQL 作为本地持久化存储。

### 1) 安装系统依赖

```bash
sudo apt update
sudo apt install -y \
  git curl build-essential \
  python3 python3-venv python3-pip \
  postgresql postgresql-contrib
```

### 2) 准备项目目录

```bash
git clone https://github.com/maniac1um/openclaw_news_publisher.git
cd openclaw_news_publisher
```

> 如果你已经在仓库目录内，可跳过该步骤。

### 3) 创建 Python 虚拟环境并安装 Python 依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### 4) 初始化 PostgreSQL

```bash
sudo systemctl enable --now postgresql
sudo -u postgres psql <<'SQL'
DO $$
BEGIN
   IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'openclaw_app') THEN
      CREATE ROLE openclaw_app LOGIN PASSWORD '请替换为强密码';
   END IF;
END$$;
SQL
```

创建数据库（首次执行）：

```bash
sudo -u postgres psql -c "CREATE DATABASE openclaw_app OWNER openclaw_app;"
```

已存在时可忽略报错，或手动检查：

```bash
sudo -u postgres psql -c "\l openclaw_app"
```

### 5) 创建 `reports` 表与索引

```bash
psql "postgresql://openclaw_app:请替换为强密码@127.0.0.1:5432/openclaw_app" <<'SQL'
CREATE TABLE IF NOT EXISTS reports (
  id BIGSERIAL PRIMARY KEY,
  ingest_id UUID NOT NULL UNIQUE,
  task_id TEXT,
  keyword TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued','processing','published','failed')),
  generated_title TEXT,
  generated_at TIMESTAMPTZ,
  payload_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reports_status_created_at ON reports (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reports_keyword_created_at ON reports (keyword, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reports_generated_at ON reports (generated_at DESC);
SQL
```

### 6) 配置环境变量（推荐写入 `.env`）

在仓库根目录创建 `.env`（或导出为 shell 环境变量）：

```bash
cat > .env <<'EOF'
OPENCLAW_DATABASE_URL=postgresql://openclaw_app:请替换为强密码@127.0.0.1:5432/openclaw_app
OPENCLAW_OPENCLAW_API_KEY=dev-openclaw-key
OPENCLAW_OPENCLAW_WS_URL=ws://localhost:18789/ws
EOF
```

### 7) 启动服务

```bash
source .venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 8) 验证服务

- 首页：`http://127.0.0.1:8000/`
- 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/healthz`
- 数据库检查：`http://127.0.0.1:8000/healthz/db`

在 **Windows 与 Ubuntu** 等多台机器上基于 GitHub 协作开发时，参见 [docs/cross-platform-development.md](docs/cross-platform-development.md)。

## 本地脚本（可直接提交 Git）

项目内 `scripts/local` 目录下脚本已改为通用、无本机私有路径和敏感信息，可直接提交并在新设备复用：

- `scripts/local/start-server.sh`
- `scripts/local/stop-server.sh`
- `scripts/local/restart-server.sh`
- `scripts/local/verify-openclaw-databases.sh`

Linux/macOS 常用：

```bash
bash scripts/local/start-server.sh
bash scripts/local/stop-server.sh
bash scripts/local/restart-server.sh
bash scripts/local/verify-openclaw-databases.sh
```

## 配置项（环境变量）

使用前缀 `OPENCLAW_`：

- `OPENCLAW_API_V1_PREFIX`（默认 `/api/v1`）
- `OPENCLAW_OPENCLAW_API_KEY`（默认 `dev-openclaw-key`）
- `OPENCLAW_OPENCLAW_ENABLE_SIGNATURE`（默认 `false`）
- `OPENCLAW_OPENCLAW_HMAC_SECRET`（默认 `dev-secret`）
- `OPENCLAW_OPENCLAW_WS_URL`（默认 `ws://localhost:18789/ws`）
- `OPENCLAW_DATABASE_URL`（可选；配置后启用 PostgreSQL 存储）
- `OPENCLAW_MONITORING_DATABASE_URL`（可选；配置后启用 PostgreSQL 价格监测存储）
- `OPENCLAW_MONITORING_ALLOW_SERVER_SCRAPE`（默认 `false`：**不在服务端**对监测 URL 做 HTTP 抓取；由 OpenClaw 采集后 `POST .../observations/ingest`。设为 `true` 可恢复旧版 `bootstrap` 批量候选 URL + `run-once` 服务端抓取）
- `OPENCLAW_MONITORING_SCHEDULER_ENABLED`（默认 `false`；仅当同时 `OPENCLAW_MONITORING_ALLOW_SERVER_SCRAPE=true` 时进程内 scheduler 才会真正启动抓取任务）
- `OPENCLAW_MONITORING_SCHEDULER_MONITOR_ID`（内部定时任务绑定的 monitor_id）
- `OPENCLAW_MONITORING_SCHEDULER_INTERVAL_MINUTES`（默认 `1440`）
- `OPENCLAW_MONITORING_SCHEDULER_RUN_ON_START`（默认 `false`，启动后是否立即跑一次）
- `OPENCLAW_CONTENT_RAW_DIR`（默认 `content/reports/raw`）
- `OPENCLAW_CONTENT_RENDERED_DIR`（默认 `content/reports/rendered`）
- `OPENCLAW_GIT_AUTO_PUSH`（默认 `false`）
- `OPENCLAW_GIT_REMOTE`（默认 `origin`）
- `OPENCLAW_GIT_BRANCH`（默认 `main`）

> 建议在生产环境通过 `.env` 或系统环境变量覆盖默认值，尤其是 API Key 与签名密钥。

## OpenClaw 接入规范

### 请求头

- `X-Api-Key`：必填，服务端鉴权。
- `X-Request-Id`：必填，幂等键组成部分。
- `X-Signature`：可选，开启签名校验时必填。

### 上报接口

`POST /api/v1/openclaw/reports`

请求体核心字段：

- `task_id`
- `keyword`
- `time_range.start` / `time_range.end`
- `sources`
- `items`
- `analysis`
- `generated_title`
- `generated_at`

返回示例：

```json
{
  "ingest_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "status": "queued"
}
```

### 状态查询

`GET /api/v1/openclaw/reports/{ingest_id}`

状态值：

- `queued`
- `processing`
- `published`
- `failed`

## 价格监测（默认：OpenClaw 采集，服务端入库）

当你配置了 `OPENCLAW_MONITORING_DATABASE_URL` 后，即可使用价格监测接口（表结构由服务端自动创建）。

**默认行为**（`OPENCLAW_MONITORING_ALLOW_SERVER_SCRAPE` 未设置或为 `false`）：

- 服务端 **不会** 对公网 URL 发起监测抓取。
- `bootstrap` 只创建 `monitor_id` 与 **一条占位 URL**（满足库表外键）；**真实价格**由 OpenClaw（或你的采集脚本）解析后，通过 **`POST .../observations/ingest`** 写入 `price_observations`。
- OpenClaw 可定时 **`GET /api/v1/public/monitoring/...`** 读取已入库的时序与观测，用于生成报告后再 **`POST /api/v1/openclaw/reports`**。

请求头（除公开 GET 外）：`X-Api-Key`。

### 1) 创建监测任务（默认模式）

`POST /api/v1/openclaw/monitoring/bootstrap`

请求体（字段仍可传入；在默认模式下 `candidate_count` / `platforms` / `source_profile` **不**用于生成大量候选抓取 URL，仅保留关键词与 `cadence` 等元数据）：

```json
{
  "keyword": "羽毛球价格",
  "candidate_count": 20,
  "platforms": ["taobao", "tmall", "jd", "news"],
  "source_profile": "auto",
  "cadence": "daily"
}
```

若将 **`OPENCLAW_MONITORING_ALLOW_SERVER_SCRAPE=true`**，`bootstrap` 会恢复为「按关键词自动生成多条候选 URL」：`source_profile` 为 `auto`（按关键词推断）、`ecommerce` 或 `commodity`（大宗商品候选以国内可访问的财经/上金所等为主）。

返回示例（默认模式常见为 1 条占位 URL）：

```json
{
  "monitor_id": "xxxx-xxxx-xxxx-xxxx",
  "inserted_urls": 1,
  "urls": ["https://openclaw.internal/ingest"]
}
```

### 2) OpenClaw 上报一条价格观测（推荐主路径）

`POST /api/v1/openclaw/monitoring/{monitor_id}/observations/ingest`

请求体示例：

```json
{
  "price": 523.4,
  "title": "页面标题或数据源说明",
  "currency": "CNY",
  "captured_at": "2026-04-10T12:00:00+08:00",
  "source_url": "https://example.com/quote",
  "raw_payload": { "vendor": "example" }
}
```

- `price` 必填；`captured_at` 可省略（使用服务器当前时间）。

### 3) 查询最近窗口期摘要（需 API Key）

`GET /api/v1/openclaw/monitoring/{monitor_id}/summary?window_days=7`

### 4) 公开读库（OpenClaw 定时拉取、无需 API Key）

- `GET /api/v1/public/monitoring/monitors`
- `GET /api/v1/public/monitoring/{monitor_id}/timeseries?window_days=30`
- `GET /api/v1/public/monitoring/{monitor_id}/observations?limit=200`

### 5) 可选：追加参考 URL（不自动触发服务端抓取，除非开启 `ALLOW_SERVER_SCRAPE`）

`POST /api/v1/openclaw/monitoring/{monitor_id}/urls`

### 6) 服务端执行一次网页采样（仅 legacy）

`POST /api/v1/openclaw/monitoring/{monitor_id}/run-once`

- 默认返回 `server_scrape_skipped: true`，**不**发起外网 HTTP。
- 仅当 **`OPENCLAW_MONITORING_ALLOW_SERVER_SCRAPE=true`** 且已配置可抓取的 URL 时才会按 URL 抓取并写入 observations。

快速调用示例（**默认：ingest + 摘要**；`BASE_URL` 与 `API_KEY` 按你的部署调整）：

```bash
BASE_URL="http://127.0.0.1:8000"
API_KEY="dev-openclaw-key"

BOOT=$(curl -sS -X POST "$BASE_URL/api/v1/openclaw/monitoring/bootstrap" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -d '{"keyword":"羽毛球价格","cadence":"daily"}')

MONITOR_ID=$(python3 -c "import sys,json; print(json.loads(sys.stdin.read())['monitor_id'])" <<< "$BOOT")

curl -sS -X POST "$BASE_URL/api/v1/openclaw/monitoring/$MONITOR_ID/observations/ingest" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -d '{"price":89.9,"currency":"CNY","title":"示例观测","source_url":"https://example.com/p"}'

curl -sS "$BASE_URL/api/v1/public/monitoring/$MONITOR_ID/observations?limit=50"

curl -sS "$BASE_URL/api/v1/openclaw/monitoring/$MONITOR_ID/summary?window_days=7" \
  -H "X-Api-Key: $API_KEY"
```

## OpenClaw 内部定时任务（仅 legacy 服务端抓取）

进程内 scheduler 会周期性调用 `run-once` 做 **HTTP 抓取**。在默认配置下 **`OPENCLAW_MONITORING_ALLOW_SERVER_SCRAPE=false`**，即使打开 `OPENCLAW_MONITORING_SCHEDULER_ENABLED`，**也不会启动**该调度器（避免空转）。

若你明确需要服务端自己爬页面，可同时设置：

```bash
export OPENCLAW_MONITORING_DATABASE_URL='postgresql://openclaw_monitor:<请替换密码>@127.0.0.1:5432/openclaw_monitor'
export OPENCLAW_MONITORING_ALLOW_SERVER_SCRAPE='true'
export OPENCLAW_MONITORING_SCHEDULER_ENABLED='true'
export OPENCLAW_MONITORING_SCHEDULER_MONITOR_ID='<monitor_id>'
export OPENCLAW_MONITORING_SCHEDULER_INTERVAL_MINUTES='60'
export OPENCLAW_MONITORING_SCHEDULER_RUN_ON_START='true'

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

状态检查：

```bash
curl -sS "http://127.0.0.1:8000/api/v1/openclaw/monitoring/scheduler/status" \
  -H "X-Api-Key: dev-openclaw-key"
```

返回字段说明（节选）：
- `enabled`: 是否开启内部 scheduler
- `started`: 当前进程是否已启动 scheduler
- `configured`: 配置是否完整（开启 + DB DSN + monitor_id）
- `allow_server_scrape`: 是否允许服务端抓取（为 `false` 时 scheduler 不会启动）

## 外部 cron / scheduler 心跳接入（可与内部并行）

如果你使用系统 `cron`、K8s `CronJob`、或其他外部调度器执行监测任务，可在每次任务完成后上报 heartbeat，让门户首页展示“最近一次执行状态”。

### 1) 上报外部任务心跳（需 API Key）

`POST /api/v1/openclaw/monitoring/external-heartbeat`

请求头：
- `Content-Type: application/json`
- `X-Api-Key: <OPENCLAW_OPENCLAW_API_KEY>`

请求体示例：

```json
{
  "job_name": "cron-monitor-hourly",
  "status": "ok",
  "monitor_id": "9551be2b-3e27-4935-a595-d1699163a3e9",
  "message": "observations ingest completed"
}
```

### 2) 公开查看外部任务最近心跳

`GET /api/v1/public/monitoring/external-jobs`

返回示例：

```json
{
  "jobs": [
    {
      "job_name": "cron-monitor-hourly",
      "status": "ok",
      "monitor_id": "9551be2b-3e27-4935-a595-d1699163a3e9",
      "message": "observations ingest completed",
      "last_seen_at": "2026-04-08T10:20:30.123456+00:00"
    }
  ]
}
```

### 3) cron 示例（OpenClaw 侧采集后 ingest，再上报 heartbeat）

默认部署下 **`run-once` 不会抓取**。推荐在外部任务里完成页面拉取与价格解析，再调用 **`observations/ingest`**，并上报心跳：

```bash
#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://127.0.0.1:8000"
API_KEY="dev-openclaw-key"
MONITOR_ID="9551be2b-3e27-4935-a595-d1699163a3e9"
JOB_NAME="openclaw-price-ingest-hourly"

# 此处省略：你的采集逻辑得到 PRICE / TITLE / SOURCE_URL
PRICE="523.4"
TITLE="cron sample"
SOURCE_URL="https://example.com/quote"

if curl -fsS -X POST "$BASE_URL/api/v1/openclaw/monitoring/$MONITOR_ID/observations/ingest" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -d "{\"price\":$PRICE,\"title\":\"$TITLE\",\"source_url\":\"$SOURCE_URL\",\"currency\":\"CNY\"}" >/dev/null; then
  STATUS="ok"
  MSG="observations ingest completed"
else
  STATUS="error"
  MSG="observations ingest failed"
fi

curl -fsS -X POST "$BASE_URL/api/v1/openclaw/monitoring/external-heartbeat" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -d "{\"job_name\":\"$JOB_NAME\",\"status\":\"$STATUS\",\"monitor_id\":\"$MONITOR_ID\",\"message\":\"$MSG\"}" >/dev/null || true
```

若已设置 **`OPENCLAW_MONITORING_ALLOW_SERVER_SCRAPE=true`**，可将上述 `ingest` 步骤替换为 `POST .../run-once` 作为旧版流程。

### 4) 运行历史持久化（新增）

从当前版本开始，`external-heartbeat` 不再只维护进程内最近状态；会同步写入监测库中的运行历史：

- `external_scheduler_runs`（运行事件流：job/status/monitor_id/message/last_seen_at/source）
- `external_scheduler_configs`（网页调度配置：cron/timezone/enabled/retry_policy）

这使得服务重启后仍可在门户端查看运行历史与配置状态。

## 网页化工作流控制台（门户首页）

门户首页新增“网页化工作流控制台”，用于把原本依赖脚本/API 的关键操作搬到页面内：

- 首次向导（关键词 -> monitor -> 外部调度配置 -> 可选立即触发联合分析）
- 一键创建监测任务（bootstrap）
- 一键保存/启停外部调度配置
- 一键触发新闻+价格联合分析并可选发布
- 查看最近外部调度运行历史（支持失败排障）

### 控制台 API 清单

- `GET /api/v1/public/workflow/state`
- `GET /api/v1/public/workflow/external-runs?limit=120`
- `GET /api/v1/public/workflow/external-configs`
- `POST /api/v1/public/workflow/external-configs`
- `POST /api/v1/public/workflow/external-configs/{job_name}/toggle`
- `POST /api/v1/public/workflow/monitor/bootstrap`
- `POST /api/v1/public/workflow/analysis/run`

### 快速调用示例（workflow/state）

```bash
curl -sS "http://127.0.0.1:8000/api/v1/public/workflow/state"
```

返回字段（节选）：

- `overview`：沿用门户工作情况聚合（报告/价格/新闻/external_cron）
- `internal_scheduler`：内部 scheduler 状态
- `external_scheduler_configs`：外部调度配置列表
- `external_scheduler_runs`：最近运行事件（含 status/message/last_seen_at）

## 门户端删除接口（可复用）

用于门户端或后续自动清理任务删除报告：
- 该接口要求配置 `OPENCLAW_DATABASE_URL`，删除 PostgreSQL 中对应报告记录；
- 同时会尝试清理同名运行时渲染文件（若存在）。

`POST /api/v1/public/reports/bulk-delete`

请求体：

```json
{
  "ingest_ids": [
    "b5f072a5-0594-46df-903c-538c3b0dee22",
    "5b21bf16-07d7-4360-b468-b570a102c0fb"
  ]
}
```

返回体：

```json
{
  "requested": 2,
  "deleted": ["..."],
  "not_found": []
}
```

## 本地联调示例（PowerShell）

```powershell
$body = @{
  task_id = "task-local-001"
  keyword = "羽毛球"
  time_range = @{
    start = "2026-03-01T00:00:00+00:00"
    end   = "2026-04-01T00:00:00+00:00"
  }
  sources = @("jd","tmall","news")
  items = @(
    @{
      title = "羽毛球价格上涨"
      source = "news"
      url = "https://example.com/a"
      published_at = "2026-03-20T10:00:00+00:00"
      price = 92.5
      currency = "CNY"
      summary = "样例摘要"
    }
  )
  analysis = "近一个月价格整体上行，波动增大。"
  generated_title = "不同时间段内羽毛球价格变化趋势分析"
  generated_at = "2026-04-01T11:00:00+00:00"
} | ConvertTo-Json -Depth 8

$resp = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/openclaw/reports" `
  -Headers @{
    "X-Api-Key" = "dev-openclaw-key"
    "X-Request-Id" = "req-local-001"
  } `
  -ContentType "application/json" `
  -Body $body

$resp
```

## 测试

```bash
pytest -q
```

## 门户聊天会话持久化

- 当前实现：门户首页聊天会话保存在浏览器 `localStorage`，刷新页面或切换门户页面后仍可恢复会话与消息。
- 会话管理：支持“新建会话”“删除当前会话”“清空缓存（删除全部本地会话）”。
- 数据约束：为避免浏览器存储膨胀，前端会限制会话总数和单会话消息条数（超限自动裁剪）。
- 边界说明：这是本地持久化，不会自动跨浏览器或跨设备同步。
- 后续扩展：如需多设备共享，可在 PostgreSQL 中落表 `chat_sessions/chat_messages` 并增加同步 API（见 `docs/architecture/news-pipeline.md`）。

## 发布链路说明

- 后台任务会将标准化报告写入运行时目录 `content/reports/rendered/{ingest_id}.json`（目录按需自动创建，默认不纳入 Git）。
- `PublishService` 调用 `scripts/publish_site.py`：
  - `git add` 渲染文件
  - 若有变更则 `git commit`
  - `OPENCLAW_GIT_AUTO_PUSH=true` 时自动 push 到远程

## 常见问题

1. 访问 `/` 返回 404
   - 确认服务是最新进程，重启后再试。

2. `/docs` 是英文界面
   - Swagger UI 框架文案默认英文；接口标题、描述与字段说明已中文化。

3. 用户页面无数据
   - 先确认 `POST /api/v1/openclaw/reports` 成功并且状态到 `published`。
   - 检查 `GET /healthz/db` 与 `reports` 表是否有对应 `ingest_id`。

4. 页面显示中文为 `???`
   - 这通常是请求发送端编码问题，建议用 UTF-8 并设置 `Content-Type: application/json; charset=utf-8`。

## 后续建议

- 完成 `retry` 接口（从 raw payload 恢复重放）。
- 增加鉴权签名、防重放与审计日志。
- 增加前端筛选（按关键词、时间范围、状态）。
- 增加数据库迁移脚本与连接池配置（生产可观测性/稳定性）。
