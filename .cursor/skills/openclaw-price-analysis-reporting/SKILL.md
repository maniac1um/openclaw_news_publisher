---
name: openclaw-price-analysis-reporting
description: 联合价格监测数据与新闻库数据生成趋势分析、事件解读与短期价格判断。用户提到价格+新闻综合分析、行情研判、新闻入库后快速判断未来趋势、日报周报月报自动生成时使用。
---

# OpenClaw 价格与新闻联合分析技能

## 必须遵守的安全准则

每次运行本 skill，均需优先检查以下限制：

- 未获得用户明确同意前，不发送测试写入请求到生产接口。
- 若服务异常或发布状态不明，不重复盲目提交，先返回错误与排查建议。
- 不伪造新闻事实、来源链接、时间戳与价格证据。
- 数据不足时输出低置信度结论，不强行下判断。

## 何时使用

当用户提出以下诉求时使用本技能：

- 对商品/资产做价格趋势分析，并结合新闻事件解释波动。
- 每次新闻入库后，希望在短时间内生成未来价格方向判断。
- 需要输出日报、周报、月报或事件快报。
- 需要把分析结果整理为 OpenClaw 报告 JSON 并可选发布。

仅做 URL 发现、纯采集配置时，不使用本技能。

## 分析模式

### A. 周期分析（Daily/Weekly/Monthly）
- 面向中长期复盘：趋势、波动、结构、风险、建议。
- 适合稳定监控品类（羽毛球、篮球等）与宏观敏感资产（BTC、黄金、原油）。

### B. 事件触发快报（News-Triggered）
- 触发条件：新闻库出现新新闻（按 `created_at` / `published_at` 判定）。
- 目标：在短时间内产出“未来短期方向判断 + 触发原因 + 风险边界”。
- 结论需标注时效窗口（如未来 24h/72h/7d）。

## 必需输入

执行前确认：

- `BASE_URL`（例：`http://127.0.0.1:8000`）
- `API_KEY`（`X-Api-Key`）
- `monitor_id`（或一组 monitor）
- 价格窗口：`window_days`（常用 7/14/30）
- 新闻窗口：`news_hours`（常用 24/72/168）
- 输出模式：`periodic` 或 `event_triggered`
- 预测时效：`horizon`（`24h` / `72h` / `7d`）
- 是否发布：`yes/no`

若关键信息缺失，先补齐再执行。

## 数据来源与接口

### 价格数据（必选）
- `GET /api/v1/openclaw/monitoring/{monitor_id}/summary?window_days={n}`
- `GET /api/v1/public/monitoring/{monitor_id}/observations?limit={n}`（如可用，用于细粒度拐点和异常波动识别）

### 新闻数据（必选）
- `GET /api/v1/public/news/library?limit={n}&keyword={kw}`
- 必要字段：`keyword`、`summary`、`source_url`、`title`、`source_name`、`published_at`、`created_at`

### 发布接口（可选）
- `POST /api/v1/openclaw/reports`
- `GET /api/v1/openclaw/reports/{ingest_id}`

## 联合分析框架（价格 x 新闻）

每份报告至少覆盖以下 8 个维度：

1. **价格水平与位置**
   - 当前均价、区间、分位位置（近窗口中的高低位）

2. **趋势与动量**
   - 上行/下行/横盘
   - 短期动量变化（最近 3-5 个采样点方向）

3. **波动与异常**
   - 振幅、相对波动、异常跳变点

4. **新闻情绪与冲击方向**
   - 对新闻做“利多/利空/中性”与强度分级（高/中/低）
   - 明确每条关键新闻对价格的可能传导方向

5. **新闻-价格时序对齐**
   - 新闻发布时间前后是否出现同向波动
   - 滞后时间（即时/数小时/1-2天）

6. **资产特异因子（按品类启用）**
   - 日用品：促销档期、渠道库存、品牌活动
   - BTC：监管、ETF/资金流、链上事件、风险偏好
   - 黄金：美元利率预期、避险情绪、央行购金
   - 原油：OPEC 政策、地缘冲突、库存与需求预期

7. **短期判断（Nowcast）**
   - 给出未来 `horizon` 方向：上行 / 下行 / 震荡
   - 输出概率或置信度（高/中/低）
   - 给出“失效条件”（例如关键位被突破）

8. **行动建议**
   - 下一轮重点关注新闻主题、监测频率与风险阈值

## 事件触发规则（新新闻后快速分析）

当用户要求“每有新闻就快速判断”时，按以下规则执行：

1. 读取最近 `news_hours` 内新闻，按 `created_at` 倒序。
2. 识别新增新闻（相对上次分析的最新时间戳）。
3. 若无新增新闻：输出“无新事件，不触发快报”。
4. 若有新增新闻：
   - 提取前 1-5 条高相关新闻（关键词匹配 + 标题/摘要相关度）。
   - 拉取对应 `monitor_id` 最新价格摘要/观测点。
   - 产出“事件快报”与未来 `horizon` 方向判断。
5. 判断结果必须附带：
   - 触发新闻列表（标题、来源、时间、链接）
   - 价格证据（均价、区间、最近采样变化）
   - 置信度与失效条件

## 报告输出模板（Markdown）

```markdown
# [主题]价格与新闻联合分析报告（[周期/快报]）

## 1. 执行摘要
- 结论一（方向 + 时效）
- 结论二（核心驱动新闻）
- 结论三（风险边界）

## 2. 核心指标
- 价格样本数：
- 有效价格样本：
- 均价 / 最低 / 最高：
- 波动幅度：
- 新闻样本数（窗口内）：

## 3. 价格趋势判断
- 趋势方向：
- 动量特征：
- 异常波动：

## 4. 新闻冲击分析
- 关键新闻1：利多/利空 + 原因
- 关键新闻2：利多/利空 + 原因
- 新闻与价格时序关系：

## 5. 短期价格判断（未来 [horizon]）
- 判断：上行/下行/震荡
- 置信度：高/中/低
- 失效条件：

## 6. 风险与不确定性
- 数据完整性风险：
- 事件突发风险：
- 模型偏差风险：

## 7. 下周期建议
1. 建议一
2. 建议二
3. 建议三
```

## 可发布 JSON 模板

当用户要求发布时，构造与 OpenClaw 入站 schema 对齐的 payload：

```json
{
  "task_id": "price-news-report-<date>-<monitor_id_short>",
  "keyword": "羽毛球价格/BTC/黄金等主题",
  "time_range": {
    "start": "2026-04-01T00:00:00+08:00",
    "end": "2026-04-08T00:00:00+08:00"
  },
  "sources": ["monitoring-summary", "news-library"],
  "items": [],
  "analysis": "本周期价格与新闻联合分析结论......",
  "generated_title": "价格与新闻联合趋势分析（YYYY-MM-DD）",
  "generated_at": "2026-04-08T09:00:00+08:00"
}
```

说明：
- `analysis` 必须包含“方向判断 + 关键新闻 + 置信度 + 风险条件”。
- `items` 可为空，但需说明基于摘要/新闻生成。
- 时间字段使用 ISO 8601。

## 工作流

执行时遵循以下清单：

```text
报告任务清单
- [ ] 校验必需输入
- [ ] 拉取价格摘要/观测数据
- [ ] 拉取新闻库数据（按关键词/时间窗）
- [ ] 评估数据质量与置信度
- [ ] 完成价格-新闻时序对齐
- [ ] 产出联合分析结论与短期判断
- [ ] 生成 Markdown 报告
- [ ] 如需发布，构建 JSON
- [ ] 如需发布，POST 到入站 API
- [ ] 轮询发布状态并返回结果
```

### 第一步：拉取价格数据

```bash
curl -sS "$BASE_URL/api/v1/openclaw/monitoring/$MONITOR_ID/summary?window_days=7" \
  -H "X-Api-Key: $API_KEY"
```

### 第二步：拉取新闻库数据

```bash
curl -sS "$BASE_URL/api/v1/public/news/library?limit=300&keyword=$KEYWORD"
```

### 第三步：联合分析与短期判断

报告中至少引用这些价格字段：
- `observations`
- `priced_observations`
- `min_price`
- `max_price`
- `avg_price`

并至少引用这些新闻字段：
- `title`
- `source_name`
- `source_url`
- `published_at`/`created_at`
- `summary`

若 `priced_observations == 0` 且无有效新闻证据，不发布强结论，仅输出低置信度建议。

### 第四步：可选发布

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

- 禁止伪造新闻来源、发布时间、价格数据与链接。
- 每条关键结论至少提供 1 条价格证据 + 1 条新闻证据（若有）。
- 观点与事实分区书写，避免混淆。
- 必须标注“判断时效窗口”和“失效条件”。
- 低置信度时不得输出确定性措辞。

## 异常处理

常见失败与处理：

- `401`：检查 `X-Api-Key`
- `404 monitor_id`：确认 monitor 是否存在
- `500/DB`：检查 `OPENCLAW_MONITORING_DATABASE_URL`、`OPENCLAW_NEWS_DATABASE_URL`
- summary 为空：先执行采样任务后重试
- 新闻为空：放宽关键词或扩大 `news_hours`

失败回执必须包含：

- 失败步骤
- 接口与状态码
- 下一条建议执行命令

## 最终回执格式

使用简洁结构：

```markdown
已完成价格与新闻联合分析报告生成。
- monitor_id: ...
- 模式: periodic/event_triggered
- 价格窗口: 7天
- 新闻窗口: 72小时
- 短期判断(24h/72h/7d): 上行/下行/震荡
- 关键驱动新闻: 2-3条
- 置信度: 高/中/低
- 是否已发布: 是/否
- ingest_id: ...（若已发布）
```
