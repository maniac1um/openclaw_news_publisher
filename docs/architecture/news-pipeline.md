# 新闻处理流水线架构

## 分层结构

- API 层（`app/api/v1/openclaw.py`）
- 入站与编排层（`app/services/intake_service.py`）
- 后台处理层（`app/workers/job_runner.py`）
- 数据与持久化层（`app/db/*`、`content/reports/*`）
- 发布适配层（`app/services/publish_service.py`、`scripts/publish_site.py`）

## 运行流程

1. OpenClaw 将报告 JSON 通过 POST 发送到 `/api/v1/openclaw/reports`。
2. API 完成鉴权、请求体结构与请求 ID 校验。
3. 入站服务基于 `X-Request-Id + task_id` 实施幂等控制。
4. 原始负载写入 `content/reports/raw/`。
5. 后台任务将数据标准化后写入 `content/reports/rendered/`。
6. 发布服务触发站点发布脚本。
7. 最终状态更新为 `published` 或 `failed`。

## 存储策略

- 原始负载（Raw）：用于追溯与回放支持。
- 渲染负载（Rendered）：为网站渲染提供稳定数据结构。

## 价格监测数据（独立库表）

价格监测使用 **`OPENCLAW_MONITORING_DATABASE_URL`** 指向的库（与 `reports` 库可分离）。默认策略下服务端 **不** 对公网页面做抓取：OpenClaw 将解析后的数值通过 **`POST /api/v1/openclaw/monitoring/{monitor_id}/observations/ingest`** 写入 `price_observations`；门户与 OpenClaw 再通过 **`GET /api/v1/public/monitoring/...`** 或带 Key 的 `summary` 读取。详见根目录 [README.md](../../README.md) 与 [docs/api/openclaw-intake.md](../api/openclaw-intake.md)。

## 门户对话持久化演进（规划）

当前门户首页聊天先采用浏览器本地持久化（`localStorage`），解决刷新与切页后会话丢失问题，适配本地单设备使用场景。若后续升级到跨设备同步，可复用主库 `OPENCLAW_DATABASE_URL` 扩展 PostgreSQL 表与 API：

- 建议表
  - `chat_sessions(session_id UUID PRIMARY KEY, user_scope TEXT, title TEXT, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)`
  - `chat_messages(id BIGSERIAL PRIMARY KEY, session_id UUID REFERENCES chat_sessions(session_id) ON DELETE CASCADE, role TEXT, content TEXT, created_at TIMESTAMPTZ)`
- 建议接口
  - `GET /api/v1/openclaw/chat/sessions`
  - `POST /api/v1/openclaw/chat/sessions`
  - `GET /api/v1/openclaw/chat/sessions/{session_id}/messages`
  - `POST /api/v1/openclaw/chat/sessions/{session_id}/messages`
  - `DELETE /api/v1/openclaw/chat/sessions/{session_id}`（可补 `bulk-delete`）
- 同步策略
  - 前端优先读本地缓存实现秒开，再异步拉服务端增量；
  - 以 `updated_at`/`created_at` 做冲突合并；
  - 服务端支持 TTL 或归档清理策略，便于控制历史消息体量。
