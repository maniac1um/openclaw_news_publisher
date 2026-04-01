---
name: openclaw-news-publisher
description: Generate keyword-focused news analysis payloads and submit them to OpenClaw News Publisher via POST. Use when the user asks to crawl news by keyword, produce trend reports, or publish structured report JSON to the website intake API.
---

# OpenClaw News Publisher Skill

## 必须遵守的安全准则
每次运行本skill，均需认真阅读文档内的限制说明！首先，你必须遵守如下的安全限制：
- 当无法接收到发布成功，服务器正常运行的反馈时，不允许再次发送或是私自发送测试请求，立刻停止运行skill，并直接向用户报错，附带网站输出的报错信息。
- 在上一条的基础上，只有在询问用户是否能发送测试请求并得到用户明确的肯定回答后，才能发送测试信息。注意！你仅仅只能发送有限的，不超过三条的测试信息，若需要发送更多的测试信息，需要再次询问获得用户的明确同意。
- 在上两条的基础上，你没有任何权限自主对用户已有的项目文件进行修改与添加。如非必要不选择自主修复bug。只有当用户明确表达帮忙修复问题时才能介入。
   
除了如上的安全限制，下文也有许多需要你注意的限制。这些限制同样不可违反！绝对不能违反这些限制，每次运行都需要检查是否违反这些限制，随时检查是否违反。如果发现违反，立刻停止服务并向用户说明情况！待用户回复之后才能重新开始。

## 适用场景

当用户提出以下意图时使用本技能：

- “按关键词抓取新闻并生成分析”
- “把分析结果提交到网站并自动更新页面”
- “围绕某主题输出价格/舆情趋势报告”
- “当用户明确说明‘在线上搜索信息：’时”

## 目标

将任务转换成可发布的报告 JSON，并调用网站接口：

- `POST /api/v1/openclaw/reports`
- 记录返回的 `ingest_id`
- 轮询 `GET /api/v1/openclaw/reports/{ingest_id}` 直到结束状态
- 如需清理历史报告，可调用批量删除接口（见下文）

## 必填请求头

- `X-Api-Key`: 网站分配的接入密钥
- `X-Request-Id`: 幂等键（重试必须复用）
- `Content-Type: application/json`

可选：

- `X-Signature`: 服务端启用签名校验时传递

## 报告 JSON 结构

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
      "title": "标题",
      "source": "来源站点",
      "url": "https://example.com/news/1",
      "published_at": "2026-03-20T10:00:00+00:00",
      "price": 89.9,
      "currency": "CNY",
      "summary": "摘要"
    }
  ],
  "analysis": "趋势分析文本",
  "generated_title": "不同时间段内羽毛球价格变化趋势分析",
  "generated_at": "2026-04-01T11:00:00+00:00"
}
```

## 执行流程

1. 解析用户意图
   - 提取 `keyword`、时间范围、关注维度（价格/政策/供需/品牌）
2. 运行爬取与抽取
   - 抓取可信来源
   - 提取发布时间、来源、链接、价格信息（若可得）
3. 生成结构化报告 JSON
   - 使用上方 schema
   - 确保 `generated_title` 与主题一致
4. 提交到网站
   - 调用 `POST /api/v1/openclaw/reports`
   - 保存返回 `ingest_id`
5. 查询状态
   - 轮询 `GET /api/v1/openclaw/reports/{ingest_id}`
   - 结束状态：`published` 或 `failed`

## 幂等与重试规则

- 同一任务重试时，必须保持 `X-Request-Id` 和 `task_id` 不变。
- 超时或网络失败时可重发 POST，但不得生成新的幂等键。
- 若状态为 `failed`，记录错误并提示可用重试接口。

## 报告清理接口（供自动删除模块调用）

当用户明确要求删除部分报告时，可调用：

- `POST /api/v1/public/reports/bulk-delete`

请求体：

```json
{
  "ingest_ids": [
    "b5f072a5-0594-46df-903c-538c3b0dee22",
    "5b21bf16-07d7-4360-b468-b570a102c0fb"
  ]
}
```

行为：

- 同步删除 `content/reports/raw/` 与 `content/reports/rendered/` 对应文件。
- 返回 `requested/deleted/not_found` 统计信息。

## 质量约束

- `sources` 与 `items[*].source` 保持一致可追溯。
- `published_at`、`generated_at` 使用 ISO 8601。
- `analysis` 要有结论，不能只罗列原文。
- `generated_title` 应是可直接面向用户展示的标题。

## 输出规范

对用户回执时至少包含：

- 任务关键词与时间范围
- 是否已提交成功
- `ingest_id`
- 当前处理状态（queued/processing/published/failed）

回执示例：

```markdown
已提交报告：不同时间段内羽毛球价格变化趋势分析
- ingest_id: 46eeaf32-a3df-403a-99c6-b4cf9b59d012
- status: queued
```
