# OpenClaw Intake API

## Endpoint

- `POST /api/v1/openclaw/reports`

## Headers

- `X-Api-Key` (required)
- `X-Request-Id` (required, idempotency key component)
- `X-Signature` (optional; required only when signature verification is enabled)

## Request Body (JSON)

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
      "title": "Example title",
      "source": "source-a",
      "url": "https://example.com/1",
      "published_at": "2026-03-20T10:00:00+00:00",
      "price": 89.9,
      "currency": "CNY",
      "summary": "..."
    }
  ],
  "analysis": "trend analysis text",
  "generated_title": "不同时间段内羽毛球价格变化趋势分析",
  "generated_at": "2026-04-01T11:00:00+00:00"
}
```

## Response

- Success: `202 Accepted`

```json
{
  "ingest_id": "uuid",
  "status": "queued"
}
```

## Status Query

- `GET /api/v1/openclaw/reports/{ingest_id}`
- Status enum: `queued`, `processing`, `published`, `failed`
