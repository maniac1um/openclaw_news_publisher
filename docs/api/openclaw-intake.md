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
