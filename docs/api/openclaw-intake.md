# OpenClaw 接入接口文档

## 接口地址

- `POST /api/v1/openclaw/reports`

## 请求头

- `X-Api-Key`（必填）
- `X-Request-Id`（必填，用于幂等键）
- `X-Signature`（可选；仅在开启签名校验时必填）

## 请求体（JSON）

```json
{
  "task_id": "task-20260401-001",
  "keyword": "羽毛球",
  "time_range": {
    "start": "2026-03-01T00:00:00+00:00",
    "end": "2026-04-01T00:00:00+00:00"
  },
  "sources": ["source-a", "source-b"],
  "items": [
    {
      "title": "示例新闻标题",
      "source": "source-a",
      "url": "https://example.com/1",
      "published_at": "2026-03-20T10:00:00+00:00",
      "price": 89.9,
      "currency": "CNY",
      "summary": "..."
    }
  ],
  "analysis": "趋势分析文本",
  "generated_title": "不同时间段内羽毛球价格变化趋势分析",
  "generated_at": "2026-04-01T11:00:00+00:00"
}
```

## 响应

- 成功：`202 Accepted`

```json
{
  "ingest_id": "uuid",
  "status": "queued"
}
```

## 状态查询

- `GET /api/v1/openclaw/reports/{ingest_id}`
- 状态枚举：`queued`、`processing`、`published`、`failed`

---

## 价格监测（OpenClaw 外采 + 服务端入库）

与报告入站相同前缀下的监测路由均在 **`/api/v1/openclaw/monitoring/...`**。完整说明与 curl 示例见仓库根目录 [README.md](../../README.md) 中的「价格监测」章节。

### 设计约定

- 默认 **`OPENCLAW_MONITORING_ALLOW_SERVER_SCRAPE=false`**：服务端不对监测 URL 做公网 HTTP 抓取；由 OpenClaw 完成采集与解析后 **`POST /api/v1/openclaw/monitoring/{monitor_id}/observations/ingest`** 写入 `price_observations`。
- **`POST .../monitoring/bootstrap`**：默认仅创建监测任务并插入一条占位 URL；`candidate_count` / `platforms` / `source_profile` 仅在开启服务端抓取时用于生成候选 URL。
- **`POST .../monitoring/{monitor_id}/run-once`**：默认返回 `server_scrape_skipped: true`；仅当 `OPENCLAW_MONITORING_ALLOW_SERVER_SCRAPE=true` 时执行 legacy 网页抓取。
- **只读拉库**（无需 `X-Api-Key`）：`GET /api/v1/public/monitoring/monitors`、`GET .../timeseries`、`GET .../observations`，供 OpenClaw 定时读取已存数据以生成报告或再 **`POST /api/v1/openclaw/reports`**。

### 鉴权

除上述 `public/monitoring` GET 外，监测写入与 `summary` 等接口均需请求头 **`X-Api-Key`**（与报告入站一致）。

### 观测入库请求体（ingest）

```json
{
  "price": 523.4,
  "title": "可选",
  "currency": "CNY",
  "captured_at": "2026-04-10T12:00:00+08:00",
  "source_url": "https://example.com/quote",
  "raw_payload": {}
}
```

- `price` 必填；`captured_at` 可省略。
