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
- 自动化发布
  - 渲染产物写入 `content/reports/rendered/`
  - 发布脚本 `scripts/publish_site.py` 执行 git add/commit（可选 push）

## 目录结构

```text
openclaw_news_publisher/
├─ app/
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
│  │  └─ publish_service.py
│  ├─ workers/job_runner.py
│  └─ main.py
├─ content/
│  └─ reports/
│     ├─ raw/
│     └─ rendered/
├─ docs/
│  ├─ api/openclaw-intake.md
│  └─ architecture/news-pipeline.md
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

## 快速开始（本地）

### 1) 安装依赖

```bash
python -m pip install -e ".[dev]"
```

### 2) 启动服务

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3) 验证服务

- 首页：`http://127.0.0.1:8000/`
- 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/healthz`

## 配置项（环境变量）

使用前缀 `OPENCLAW_`：

- `OPENCLAW_API_V1_PREFIX`（默认 `/api/v1`）
- `OPENCLAW_OPENCLAW_API_KEY`（默认 `dev-openclaw-key`）
- `OPENCLAW_OPENCLAW_ENABLE_SIGNATURE`（默认 `false`）
- `OPENCLAW_OPENCLAW_HMAC_SECRET`（默认 `dev-secret`）
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

用于门户端或后续自动清理任务删除报告文件（raw + rendered 同步删除）：

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
   - 检查 `content/reports/rendered/` 是否生成 JSON 文件。

4. 页面显示中文为 `???`
   - 这通常是请求发送端编码问题，建议用 UTF-8 并设置 `Content-Type: application/json; charset=utf-8`。

## 后续建议

- 将内存仓储替换为数据库（SQLite/PostgreSQL）。
- 完成 `retry` 接口（从 raw payload 恢复重放）。
- 增加鉴权签名、防重放与审计日志。
- 增加前端筛选（按关键词、时间范围、状态）。
