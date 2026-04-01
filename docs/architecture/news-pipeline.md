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
