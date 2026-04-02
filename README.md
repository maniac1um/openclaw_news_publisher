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
- OpenClaw 门户聊天（FastAPI WebSocket）
  - 首页聊天框：OpenClaw 回复在左侧气泡、用户消息在右侧气泡实时展示
  - 中转接口：`WS /api/v1/chat/ws`（服务端连接 OpenClaw Gateway，并将流式增量内容按 `200ms` 聚合后推送前端）
- 用户页面与公开查询 API
  - `/`（新闻动态：首页报告列表 + Markdown 详情）
  - `/topic-analysis`（专题分析：开发中）
  - `/price-trend`（价格趋势：开发中）
  - `/keyword-tracking`（关键词追踪：开发中）
  - `GET /api/v1/public/reports`
  - `GET /api/v1/public/reports/{ingest_id}`
  - `POST /api/v1/public/reports/bulk-delete`（批量删除）
- 文档与运维
  - `/docs`（Swagger）
  - `/healthz`（健康检查）
  - `/healthz/db`（数据库连通性检查；未配置数据库时返回 enabled=false）
- 自动化发布
  - 渲染产物写入 `content/reports/rendered/`
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
├─ content/
│  └─ reports/
│     ├─ raw/
│     └─ rendered/
├─ docs/
│  ├─ api/openclaw-intake.md
│  ├─ architecture/news-pipeline.md
│  └─ cross-platform-development.md
├─ scripts/publish_site.py
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

## 配置项（环境变量）

使用前缀 `OPENCLAW_`：

- `OPENCLAW_API_V1_PREFIX`（默认 `/api/v1`）
- `OPENCLAW_OPENCLAW_API_KEY`（默认 `dev-openclaw-key`）
- `OPENCLAW_OPENCLAW_ENABLE_SIGNATURE`（默认 `false`）
- `OPENCLAW_OPENCLAW_HMAC_SECRET`（默认 `dev-secret`）
- `OPENCLAW_OPENCLAW_WS_URL`（默认 `ws://localhost:18789/ws`）
- `OPENCLAW_DATABASE_URL`（可选；配置后启用 PostgreSQL 存储）
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

## 门户端删除接口（可复用）

用于门户端或后续自动清理任务删除报告：
- 配置了 `OPENCLAW_DATABASE_URL` 时：删除 PostgreSQL 中对应记录；
- 未配置数据库时：删除 `content/reports/raw/` 与 `content/reports/rendered/` 对应文件。

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

## 发布链路说明

- 后台任务将标准化报告写入 `content/reports/rendered/{ingest_id}.json`。
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
   - 若启用数据库：检查 `GET /healthz/db` 与 `reports` 表是否有对应 `ingest_id`。
   - 若未启用数据库：检查 `content/reports/rendered/` 是否生成 JSON 文件。

4. 页面显示中文为 `???`
   - 这通常是请求发送端编码问题，建议用 UTF-8 并设置 `Content-Type: application/json; charset=utf-8`。

## 后续建议

- 完成 `retry` 接口（从 raw payload 恢复重放）。
- 增加鉴权签名、防重放与审计日志。
- 增加前端筛选（按关键词、时间范围、状态）。
- 增加数据库迁移脚本与连接池配置（生产可观测性/稳定性）。
