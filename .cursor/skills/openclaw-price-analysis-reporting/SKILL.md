---
name: openclaw-price-analysis-reporting
description: 基于 OpenClaw 价格监测数据生成高质量趋势分析报告，并可选发布到 OpenClaw 入站 API。用户提到价格趋势、周报月报、波动分析、监测数据自动成报时使用。
---

# OpenClaw 价格分析报告技能

## 何时使用

当用户提出以下诉求时使用本技能：

- 分析历史价格监测数据（而非只采集）。
- 生成日报、周报、月报等趋势报告。
- 输出趋势方向、波动特征、结构差异与风险判断。
- 将监测摘要转换为可发布的 OpenClaw 报告 JSON。
- 可选调用 `POST /api/v1/openclaw/reports` 自动发布。

仅做爬虫配置或 URL 发现时，不使用本技能。

## 必需输入

生成报告前，确认以下输入：

- `BASE_URL`（例：`http://127.0.0.1:8000`）
- `API_KEY`（`X-Api-Key`）
- `monitor_id`
- 分析窗口（`window_days`，常用 7/14/30）
- 报告周期（`daily` / `weekly` / `monthly`）
- 是否发布（`yes/no`）

若关键信息缺失，先用简洁问题补齐后再执行。

## 数据来源

主数据接口：

- `GET /api/v1/openclaw/monitoring/{monitor_id}/summary?window_days={n}`
- 可选：用户提供的自定义 SQL 聚合结果或观测数据导出。

可选上下文：

- 促销日历（618、双11 等）
- 品牌分层信息
- 平台关注范围（taobao/tmall/jd/news）

## 分析框架（高质量标准）

每份报告至少覆盖以下六个维度：

1. **价格水平**
   - 当前窗口均价
   - 最低价 / 最高价区间
   - 相对上个可比窗口的绝对变化与百分比变化

2. **趋势方向**
   - 上行 / 下行 / 横盘
   - 短中期走势是否一致
   - 是否出现拐点（数据支持时）

3. **波动性**
   - 振幅（max-min）
   - 相对波动（振幅 / 均价）
   - 异常涨跌日（如可识别）

4. **结构差异**
   - 平台间差异
   - 品牌/规格分层差异（有数据时）
   - 高价/低价样本对整体均价的贡献

5. **数据质量与置信度**
   - 总观测数
   - 有效价格观测数
   - 缺失/失败占比
   - 置信度：高 / 中 / 低

6. **可执行建议**
   - 下周期重点监测项
   - 潜在风险因素
   - 运营动作建议

## 报告输出模板（Markdown）

主要按以下结构生成，如有必要可以进行增减：

```markdown
# [主题]价格趋势分析报告（[周期]）

## 1. 执行摘要
- 结论1（1句话）
- 结论2（1句话）
- 结论3（1句话）

## 2. 核心指标
- 样本数：
- 有效价格样本：
- 均价：
- 最低价 / 最高价：
- 波动幅度：

## 3. 趋势判断
- 趋势方向：
- 阶段特征：
- 关键拐点：

## 4. 结构分析
- 平台差异：
- 品牌/规格差异：
- 异常值说明：

## 5. 风险与不确定性
- 数据完整性风险：
- 价格识别偏差风险：
- 外部事件风险：

## 6. 下周期建议
1. 建议一
2. 建议二
3. 建议三
```

## 可发布 JSON 模板

当用户要求发布时，构造与 OpenClaw 入站 schema 对齐的 payload：

```json
{
  "task_id": "price-report-<date>-<monitor_id_short>",
  "keyword": "羽毛球价格",
  "time_range": {
    "start": "2026-04-01T00:00:00+08:00",
    "end": "2026-04-08T00:00:00+08:00"
  },
  "sources": ["monitoring-summary"],
  "items": [],
  "analysis": "本周期整体价格呈......",
  "generated_title": "羽毛球价格周度趋势分析（YYYY-MM-DD）",
  "generated_at": "2026-04-08T09:00:00+08:00"
}
```

说明：

- `analysis` 必须是具体结论，不能是占位文本。
- 若 `items` 为空，需明确说明这是基于观测摘要生成的报告。
- 所有时间字段均使用 ISO 8601。

## 工作流

执行时遵循以下清单：

```text
报告任务清单
- [ ] 校验必需输入
- [ ] 拉取监测摘要数据
- [ ] 评估数据质量与置信度
- [ ] 按六维框架生成分析
- [ ] 产出 Markdown 报告
- [ ] 如需发布，构建 JSON
- [ ] 如需发布，POST 到入站 API
- [ ] 轮询发布状态并返回结果
```

### 第一步：拉取 summary

示例：

```bash
curl -sS "$BASE_URL/api/v1/openclaw/monitoring/$MONITOR_ID/summary?window_days=7" \
  -H "X-Api-Key: $API_KEY"
```

### 第二步：生成结论

报告中至少引用以下指标：

- `observations`
- `priced_observations`
- `min_price`
- `max_price`
- `avg_price`

若 `priced_observations == 0`，停止发布流程，输出“低置信度结论”并给出修复建议：

- 通过 `/monitoring/{monitor_id}/urls` 增加高质量商品详情页 URL
- 重新执行采样

### 第三步：可选发布

提交：

```bash
curl -sS -X POST "$BASE_URL/api/v1/openclaw/reports" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -H "X-Request-Id: <uuid>" \
  -d @report_payload.json
```

轮询：

```bash
curl -sS "$BASE_URL/api/v1/openclaw/reports/$INGEST_ID" \
  -H "X-Api-Key: $API_KEY"
```

## 质量规则

- 禁止伪造来源 URL 或原始事实。
- 数据不完整时必须显式标注假设。
- 观察事实与行动建议分开写。
- 所有结论都要可回溯到数值证据。
- 置信度低时直接说明，不做强结论。

## 异常处理

常见失败与处理：

- `401`：检查 `X-Api-Key`
- `404 monitor_id`：确认 monitor 是否存在
- `500/DB`：检查 `OPENCLAW_MONITORING_DATABASE_URL` 与数据库账号密码
- summary 为空：先执行 `run-once` 再重试

失败回执必须包含：

- 失败步骤
- 接口与状态码
- 下一条建议执行命令

## 最终回执格式

使用简洁结构：

```markdown
已完成价格分析报告生成。
- monitor_id: ...
- 窗口: 7天
- 结论: ...
- 置信度: 高/中/低
- 是否已发布: 是/否
- ingest_id: ...（若已发布）
```

