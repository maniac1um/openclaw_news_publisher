---
name: openclaw-price-analysis-reporting
description: 对齐 OpenClaw News Publisher 三库架构与报告入站 schema；联合价格监测与新闻库做多窗口分析、历史报告复盘与结构化短期研判，并可 POST 报告或调用服务端 news-trigger 辅助落库。
---

# OpenClaw 价格与新闻联合分析技能（与服务器结构对齐）

本技能用于指导 OpenClaw（或 Cursor Agent）在 **已部署的 News Publisher** 上：读取监测库价格、读取新闻库、可选读取 **已发布的历史报告**，生成 **可追溯、可审计** 的联合分析，并按需 **`POST /api/v1/openclaw/reports`** 落库与门户展示。

**重要声明**：任何「未来行情」输出均为 **概率性、可失效** 的情景判断，不是投资建议；须遵守数据与引用纪律，禁止伪造价格与新闻。

## 必须遵守的安全准则

每次运行本 skill，均需优先检查以下限制：

- 未获得用户明确同意前，不发送测试写入请求到生产接口。
- 若服务异常或发布状态不明，不重复盲目提交，先返回错误与排查建议。
- 不伪造新闻事实、来源链接、时间戳与价格证据。
- 数据不足时输出低置信度结论，不强行下判断。

---

## 1. 与本地服务器结构对齐（必读）

### 1.1 三套 PostgreSQL 数据源

服务端按环境变量使用 **三个可分离的** 数据库（可同机不同库名）：

| 环境变量 | 典型用途 | 未配置时的表现 |
|----------|----------|----------------|
| `OPENCLAW_DATABASE_URL` | 主库：`reports` 表；报告入站、门户专题/报告列表与详情 | 入站可能走内存模式；**`GET /api/v1/public/reports*` 返回 503** |
| `OPENCLAW_MONITORING_DATABASE_URL` | 监测库：`price_monitors` / `price_monitor_urls` / `price_observations` | 价格相关 API 空数据或 503 |
| `OPENCLAW_NEWS_DATABASE_URL` | 新闻库：`news_library` | **`GET /api/v1/public/news/library` 503** |

执行本技能前，应用 `GET /healthz`；若已配置主库可再测 `GET /healthz/db`。本地自检可运行：`bash scripts/local/verify-openclaw-databases.sh`（仓库根目录，读取 `.env`）。

### 1.2 请求基址与鉴权

- **`BASE_URL`**：例如 `http://127.0.0.1:8000`（按实际部署修改）。
- **`API_KEY`**：请求头 **`X-Api-Key`**，对应环境变量 **`OPENCLAW_OPENCLAW_API_KEY`**（Pydantic 前缀 `OPENCLAW_` + 字段名 `openclaw_api_key`，故为双段 `OPENCLAW_`）。
- **报告入站** `POST /api/v1/openclaw/reports` 还必须带 **`X-Request-Id`**（幂等键；缺失返回 **400**）。同一 `X-Request-Id` + 相同 `task_id` 重试应返回已有 `ingest_id`。
- 若服务端开启签名校验，还需 **`X-Signature`**（见 `docs/api/openclaw-intake.md`）。

### 1.3 无「一键聚合」读接口

不存在单条 HTTP 返回「价格 + 新闻 + 历史报告」的合并接口。标准做法是 **多次 GET**，在 OpenClaw 侧组装上下文后再调用模型生成结论。

---

## 2. 何时使用本技能

- 用户要做 **价格 + 新闻** 的综合解读、日报/周报/月报、或 **新闻入库后的短期方向** 研判。
- 用户希望 **引用历史已发布报告** 做纵向对比与话术校准。
- 用户要将结论 **发布到门户**（`POST .../openclaw/reports` 或带 `publish: true` 的 `news-trigger`）。

**不使用**本技能：仅配置监测 URL、仅 bootstrap、与联合分析无关的纯运维操作。

---

## 3. 两条实现路径（择一或组合）

### 路径 A — 服务端轻量「新闻触发」模板（快速、规则化）

当用户接受 **服务端内置规则**（摘要 + 简单多空计数 + 模板化 `analysis`）时：

- **`POST /api/v1/openclaw/analysis/news-trigger`**
- 请求头：`Content-Type: application/json`、`X-Api-Key: <API_KEY>`
- 请求体字段（与代码一致）：

```json
{
  "monitor_id": "<uuid>",
  "keyword": null,
  "window_days": 7,
  "news_hours": 72,
  "horizon": "24h",
  "publish": false
}
```

- `keyword` 可省略，服务端会用该 monitor 的 keyword。
- 该路径默认是**单关键词语义**：并非扫描全库全部新闻，而是以请求 `keyword`（或 monitor 关键词）过滤新闻后再做窗口筛选。
- `publish: true` 时会在服务端组装 **`OpenClawReportIn`** 并入队（内部同样要求幂等逻辑；实现使用基于时间戳的 `request_id`）。
- 返回体含 `summary`、`key_news`、`forecast`、`confidence`、`analysis` 等；**深度叙事与多窗口仍建议路径 B 补充**。

### 路径 B — OpenClaw 侧「深度联合分析」（推荐用于长期数据与可解释预测）

由 Agent **自行拉数、自行撰写 `analysis`**，再按需 `POST /api/v1/openclaw/reports`。下文章节默认路径 B。

---

## 4. 数据接口清单（与当前实现对齐）

### 4.1 价格（监测库）

| 接口 | Key | 说明 |
|------|-----|------|
| `GET /api/v1/public/monitoring/monitors` | 否 | 列表：`monitor_id`、`keyword`、`observation_count`、`last_captured_at` 等 |
| `GET /api/v1/public/monitoring/{monitor_id}/timeseries?window_days={1-365}` | 否 | 按日聚合点（默认 `window_days=30`） |
| `GET /api/v1/public/monitoring/{monitor_id}/observations?limit={1-1000}` | 否 | 明细行；**当前实现为按 `captured_at` 升序取前 `limit` 条**（时间轴上偏早的一段，未必是「最近」）。做 **近期拐点** 时请优先 **`summary` + `timeseries`**，或明确知晓该排序语义后再用 observations。 |
| `GET /api/v1/openclaw/monitoring/{monitor_id}/summary?window_days={n}` | **是** | 窗口内 `min_price` / `max_price` / `avg_price` / `latest_price` / `priced_observations` 等，适合质量评估与报告引用 |

默认 **`OPENCLAW_MONITORING_ALLOW_SERVER_SCRAPE=false`**：不在服务端爬公网；价格样本由 OpenClaw **`POST /api/v1/openclaw/monitoring/{monitor_id}/observations/ingest`** 写入（见 `openclaw-price-ingest-external` 技能）。

### 4.2 新闻（新闻库）

- **`GET /api/v1/public/news/library?limit={1-500}&keyword={可选}`**
- 字段：`id`、`keyword`、`summary`、`source_url`、`title`、`source_name`、`published_at`、`created_at`
- 分析时同时参考 **`published_at`** 与 **`created_at`**，与价格采样时间对齐时写清楚所用字段。
- 当前新闻库的主分类依据是入库时写入的 `keyword` 字段（标签式分类）；并非内置多级主题树。
- 若需要“综合宏观 + 行业 + 事件”联合分析，应在路径 B 中按**多个关键词**分别查询并在 OpenClaw 侧合并去重，而不是依赖单次单关键词请求。

### 4.3 历史已发布报告（主库，用于「长期积累」与复盘）

需配置 **`OPENCLAW_DATABASE_URL`**：

- **`GET /api/v1/public/reports`**：列表项含 `ingest_id`、`title`、`keyword`、`generated_at` 等（仅 **已发布** 且含 `rendered_payload` 的记录）。
- **`GET /api/v1/public/reports/{ingest_id}`**：详情含渲染字段；可将其中 **`analysis`**、标题、时间范围与 **当前多窗口结论** 对照，写「与历史判断一致性 / 偏差原因」。

**可选**：`GET /api/v1/public/topic/cards`、`GET /api/v1/public/news/items` — 门户专题相关，可作补充上下文。

### 4.4 报告发布与状态

- **`POST /api/v1/openclaw/reports`** + `X-Api-Key` + **`X-Request-Id`** + JSON body（见第 7 节 schema）。
- **`GET /api/v1/openclaw/reports/{ingest_id}`**：`queued` → `processing` → `published` / `failed`。

---

## 5. 长期数据与「较有效」预测的实操规范

模型无法保证预测准确；以下规范用于 **提高信息利用率与可复盘性**。

### 5.0 当前能力边界（防误用）

- 当前服务端 `news-trigger` 适合快速模板化分析，但新闻检索本质偏单关键词。
- 想要做“黄金 + 利率 + 地缘 + 风险偏好”等多类联合，请优先使用路径 B 的多关键词聚合策略。
- 当数据库内暂时缺乏多类新闻时，允许自动降级为单类新闻分析，但必须显式降低置信度并提示覆盖不足。

### 5.1 多时间尺度（强制建议）

对同一 `monitor_id` 至少拉 **两档或以上** `window_days`，例如 **7 + 30** 或 **7 + 30 + 90**（均需在 `1–365`）：

- **短窗**：噪声、事件后即时反应。
- **中长窗**：趋势与区间位置。

在报告中分小节写清各窗口的 `min/max/avg/latest` 与 **结论是否跨窗口一致**；若矛盾，优先说明矛盾来源（采样稀疏、单条异常价、新闻滞后等）。

### 5.2 历史报告对照（强制建议，若主库可用）

1. `GET /api/v1/public/reports`，筛选与当前 **`keyword` 或 monitor 主题** 相关的最近 **3～10** 条。
2. 对每条通过 `GET .../reports/{ingest_id}` 读取 `analysis` 与 `time_range`。
3. 在当期报告中增加 **「历史判断回顾」**：此前结论、覆盖区间、与后续实际价格区间是否大致一致；若不一致，说明可能原因（数据不足、外生冲击、监测口径变化）。

### 5.3 数据充分性门槛（强制）

在写入 `analysis` 前自检（可从 `summary` 读取）：

| 条件 | 建议 |
|------|------|
| `priced_observations` &lt; 5 | 仅允许 **低** 置信度；禁止强单边措辞；列出补采建议 |
| `priced_observations` 5～19 | 最高 **中** 置信度 |
| `priced_observations` ≥ 20 且关键新闻 ≥ 2 | 可给 **高** 置信度，但仍须写失效条件 |

新闻侧：窗口内有效条数为 0 时，不得把波动主要归因于「新闻冲击」；应写数据缺失。

### 5.3A 置信度评分（100 分制，强制建议）

在 `analysis` 产出前，建议计算综合分并映射为高/中/低：

- `DataScore`（0~40）：基于 `priced_observations` 与价格覆盖完整度。
- `WindowConsistency`（0~20）：7/30/90 窗口方向是否一致。
- `NewsAlignment`（0~25）：关键新闻与价格拐点的时间对齐程度。
- `HistoricalCalibration`（0~15）：历史同类报告判断与后续走势的一致性。

映射建议：

- `>= 75`：高
- `45~74`：中
- `< 45`：低

降级约束：

- 进入 `single_class_fallback` 时，置信度不得高于 **中**。
- 仅单条新闻或新闻时间无法对齐时，置信度不得高于 **中**。

### 5.4 新闻—价格时序对齐（强制）

对每条「关键新闻」列出：`published_at`/`created_at`、并说明其相对 **最近若干价格观测或日聚合点** 的先后关系（即时 / 数小时 / 1～2 日滞后）。禁止无法对齐的因果断言。

### 5.4A 多类新闻优先与单类降级（强制）

本技能默认采用 **多类新闻联合**，即围绕资产主题自动生成关键词篮子，而不是每次手工改词。

- 目标：避免仅靠单一关键词造成信息偏差（例如只看商品名，忽略宏观、政策、供需和风险事件）。
- 执行方式：对任意 `keyword` 先做 **关键词篮子自动扩展**，再按扩展结果分别请求新闻库并合并去重。

关键词篮子自动扩展规则（通用于未来新商品）：

1. **核心同义词层（必选）**  
   由输入 `keyword` 生成同义词/别名/英文简称（如有），通常 2~6 个词。
2. **宏观驱动层（通用）**  
   固定加入宏观词组（如利率、通胀、汇率、就业、风险偏好、地缘冲突）。
3. **供需产业链层（按品类）**  
   从 `keyword` 推断品类后，补充上游/下游/库存/运输/政策等词组。
4. **事件风险层（通用）**  
   补充监管、制裁、突发事件、重大会议等冲击词组。
5. **历史自学习层（可选）**  
   从最近历史报告提取高频有效词，加入下一轮篮子（仅增补，不替代核心词）。

最小执行要求：

- 单次分析至少使用 **3 个主题维度**（核心 + 宏观 + 行业/事件任一）。
- 每个维度建议 2~5 个词；总关键词数建议 6~20，避免过宽导致噪声。

**自动降级规则**（满足你当前“库内新闻不足”的场景）：

1. 先尝试多类关键词拉取并合并新闻。
2. 若有效新闻仅来自单一关键词，或多类关键词总有效条数不足（建议 `< 3`）：
   - 自动降级为 **单类新闻分析**（`single_class_fallback`）。
   - 置信度上限降为 **中**；若 `priced_observations < 5` 则仍为 **低**。
   - 在 `analysis` 明确写出：`新闻覆盖不足，已降级为单类分析，结论稳健性受限`。
3. 若窗口内无有效新闻：
   - 只给价格侧观察结论，禁止给“新闻驱动”因果断言。

### 5.5 品类 Playbook（按需启用）

在 `keyword` 或 monitor 名称可判断品类时，启用对应因子清单（与旧版技能一致，可扩展）：

- 日用品：促销、渠道、库存、品牌活动。
- BTC：监管、ETF/资金流、链上、风险偏好。
- 黄金：利率预期、避险、央行行为。
- 原油：OPEC、地缘、库存与需求。

### 5.5A 通用品类映射速查表（用于关键词篮子自动扩展）

当输入 `keyword` 不是固定内置示例时，按下表先判断“资产品类”，再自动补充扩展词组。若无法明确归类，使用“通用资产”行并提高不确定性说明。

| 品类 | 常见识别线索（keyword 命中） | 自动扩展优先维度 | 建议扩展词（示例） |
|------|------------------------------|------------------|-------------------|
| 贵金属 | 黄金、白银、铂金、钯金、XAU、XAG | 宏观利率、汇率、避险、央行 | 美联储、实际利率、美元指数、通胀、地缘冲突、央行购金 |
| 能源 | 原油、布伦特、WTI、天然气、煤炭、电力 | 供需、库存、运输、地缘、政策 | OPEC、库存、航运、炼厂开工、制裁、产量、能源政策 |
| 农产品 | 大豆、玉米、小麦、棉花、糖、咖啡、油脂 | 天气、种植/收割、库存、出口政策 | 干旱、降雨、播种面积、USDA、库存、出口限制、关税 |
| 工业金属 | 铜、铝、镍、锌、锡、铁矿石、螺纹钢 | 制造业景气、地产/基建、库存、供给扰动 | PMI、基建、矿山事故、冶炼产能、港口库存、进口数据 |
| 化工材料 | 橡胶、塑料、PTA、乙二醇、甲醇 | 上游原料、装置开工、下游需求、运价 | 原油成本、装置检修、下游开工、海运费、库存变化 |
| 消费品 | 羽毛球、运动装备、家电、食品饮料、日用品 | 促销、渠道、库存、消费信心、替代品 | 电商大促、渠道补库、品牌活动、社零、替代品价格 |
| 航运物流 | 集运、干散货、运价指数、港口吞吐 | 运力、港口拥堵、贸易流、油价成本 | 航线运力、港口拥堵、红海/运河、BDI、燃油成本 |
| 汇率/利率 | 美元指数、人民币汇率、国债收益率、政策利率 | 宏观数据、央行政策、风险偏好 | CPI、非农、议息会议、财政政策、避险情绪 |
| 加密资产 | BTC、ETH、比特币、以太坊、稳定币 | 监管、ETF/资金流、链上活动、风险偏好 | ETF净流入、交易所资金、链上活跃地址、监管政策、黑客事件 |
| 股票/指数 | A股、美股、恒生、纳指、行业指数 | 盈利预期、政策、流动性、风险偏好 | 财报季、回购、政策信号、估值、利率预期 |
| 通用资产（兜底） | 无法明确归类 | 宏观、政策、突发事件 | 利率、通胀、汇率、地缘冲突、监管、需求变化 |

使用规则：

1. 先从 `keyword` 识别主品类（可多标签）；命中多类时以业务相关度排序，最多取 2 类。
2. 每个品类至少抽取 1 组“行业维度词”，并叠加“宏观维度词”。
3. 最终关键词篮子应覆盖：`核心同义词 + 宏观 + 行业/供需 + 事件风险` 四层中的至少三层。
4. 若归类不确定，必须在 `analysis` 写明“品类映射不确定，结论稳健性受限”。

### 5.6 结构化预测块（写入 `analysis` 文末固定小节）

在 Markdown 风格 `analysis` 末尾增加如下小节（便于人与后续自动化解析）：

```markdown
## 预测与校准（非投资建议）
- **horizon**：例如未来 24h / 72h / 7d
- **基准情景**：上行 | 下行 | 震荡（三选一或分配主观权重）
- **置信度**：高 | 中 | 低（须与 §5.3 门槛一致）
- **关键假设**：列出 2～4 条
- **失效条件**：客观可观察条件（价位突破、时间窗届满、某类新闻出现等）
- **若判断错误**：下一步如何更新监测与新闻关键词
```

---

## 6. 联合分析内容框架（价格 × 新闻）

每期报告正文建议覆盖以下维度（可与 §5.6 合并排版）：

1. 价格水平与区间位置（多窗口）  
2. 趋势与动量（结合 timeseries 与日聚合）  
3. 波动与异常点（注明是否单点噪声）  
4. 新闻情绪与传导方向（利多/利空/中性 + 强度）  
5. 新闻—价格时序对齐（§5.4）  
6. 品类特异因子（§5.5）  
7. 短期情景判断（与 horizon 一致）  
8. 下周期监测与采集建议（频率、关键词、风险阈值）  

---

## 7. 报告入站 JSON（与 `OpenClawReportIn` 一致）

发布前 body 必须符合服务端 Pydantic 模型（见 `app/schemas/report.py`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 非空；建议含日期与 monitor 短前缀 |
| `keyword` | string | 非空 |
| `time_range` | object | `start`、`end`：**ISO 8601** |
| `sources` | string[] | 例如 `["monitoring-summary","news-library","public-reports-history"]` |
| `items` | array | 元素为 `NewsItem`：`title`、`source`、`url`、`published_at` 必填；`price`、`currency`、`summary` 可选。**允许 `[]`**，但若为空须在 `analysis` 中说明「无结构化条目，仅基于摘要/聚合数据」 |
| `analysis` | string | 完整分析正文（含 §5.3～5.6） |
| `generated_title` | string | 展示用标题 |
| `generated_at` | string | ISO 8601 |

**`items` 填充建议**：从新闻库选取 3～12 条关键新闻，每条映射为一条 `NewsItem`（`source` ← `source_name`，`url` ← `source_url`）；`published_at` 优先用新闻 `published_at`，否则 `created_at`。

---

## 7A. 逻辑流程（纯逻辑设计稿落地）

```text
开始
  -> 收集输入(monitor_id, keyword, horizon, window_set=[7,30,90], news_hours)
  -> 拉取价格数据(summary + timeseries)
  -> 多类关键词拉取新闻并合并去重
       -> 若多类新闻不足: 切换 single_class_fallback 并限制置信度上限
  -> 拉取历史报告并做校准(可用则执行)
  -> 数据质量评估(不足则输出低置信度观察报告)
  -> 事件-价格时间对齐(lead/同步/lag)
  -> 生成三情景(基准/乐观/悲观)
  -> 计算置信度并检查上限约束
  -> 组装 analysis + items + 失效条件
  -> 可选发布与状态轮询
结束
```

## 8. 工作流清单（路径 B）

```text
- [ ] 确认 BASE_URL、API_KEY、monitor_id、keyword、horizon、是否发布
- [ ] 多窗口拉取 summary（及 timeseries）
- [ ] 按“关键词篮子自动扩展规则”生成多类关键词并拉取新闻；不足时自动切换 single_class_fallback
- [ ] 拉取历史 public/reports 并做对照（若 503 则跳过并注明主库未配置）
- [ ] 执行 §5.3 数据充分性自检
- [ ] 撰写 analysis（含 §5.4 时序对齐、§5.5 品类因子、§5.6 预测块，并写明是否发生 single_class_fallback）
- [ ] 组装 items 与 time_range
- [ ] 若发布：生成唯一 X-Request-Id，POST /openclaw/reports，轮询至 published 或 failed
- [ ] 回执 ingest_id、置信度、数据窗口摘要
```

---

## 9. 命令示例（路径 B 片段）

```bash
export BASE_URL="http://127.0.0.1:8000"
export API_KEY="dev-openclaw-key"
export MONITOR_ID="<uuid>"
export KEYWORD="羽毛球"

# 多窗口摘要（需 Key）
curl -sS "$BASE_URL/api/v1/openclaw/monitoring/$MONITOR_ID/summary?window_days=7"  -H "X-Api-Key: $API_KEY"
curl -sS "$BASE_URL/api/v1/openclaw/monitoring/$MONITOR_ID/summary?window_days=30" -H "X-Api-Key: $API_KEY"

# 公开时序（无需 Key）
curl -sS "$BASE_URL/api/v1/public/monitoring/$MONITOR_ID/timeseries?window_days=30"

# 新闻库
curl -sS "$BASE_URL/api/v1/public/news/library?limit=200&keyword=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$KEYWORD")"

# 多关键词联合（路径 B 推荐）：关键词篮子由“自动扩展规则”生成
# 例：把自动扩展后的结果放到 KW_LIST（而不是写死某个商品）
KW_LIST=("{{核心词1}}" "{{核心词2}}" "{{宏观词1}}" "{{供需词1}}" "{{事件词1}}")
for KW in "${KW_LIST[@]}"; do
  curl -sS "$BASE_URL/api/v1/public/news/library?limit=120&keyword=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$KW")"
done

# 历史报告
curl -sS "$BASE_URL/api/v1/public/reports"
curl -sS "$BASE_URL/api/v1/public/reports/<ingest_id>"

# 发布（X-Request-Id 必填；请使用新生成的 UUID）
curl -sS -X POST "$BASE_URL/api/v1/openclaw/reports" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -H "X-Request-Id: $(python3 -c "import uuid; print(uuid.uuid4())")" \
  -d @report_payload.json
```

路径 A 示例：

```bash
curl -sS -X POST "$BASE_URL/api/v1/openclaw/analysis/news-trigger" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -d "{\"monitor_id\":\"$MONITOR_ID\",\"window_days\":7,\"news_hours\":72,\"horizon\":\"24h\",\"publish\":false}"
```

---

## 10. 异常与排查

| 现象 | 处理方向 |
|------|----------|
| `401` / 鉴权失败 | 检查 `X-Api-Key` 与 `OPENCLAW_OPENCLAW_API_KEY` |
| `400` Missing `X-Request-Id` | 报告 POST 必须带该头 |
| `503` 含未配置 `OPENCLAW_NEWS_DATABASE_URL` | 配置新闻库 DSN；news-trigger 亦依赖新闻库 |
| `503` 含未配置监测库 | 配置 `OPENCLAW_MONITORING_DATABASE_URL` |
| `503` / public reports 不可用 | 配置 `OPENCLAW_DATABASE_URL` 并确保 `reports` 表存在 |
| `404` report / monitor | 检查 id |
| 入站 `failed` | `GET .../openclaw/reports/{ingest_id}` 读 `error`；常见为磁盘权限或可选 `publish_site` 脚本失败 |

失败回执须包含：**步骤、URL、HTTP 状态、服务端 `detail` 或 `error` 字段、建议下一步**。

---

## 11. 安全与合规（补充）

除上文 **「必须遵守的安全准则」** 外，还须注意：

- 不在输出中泄露 `.env` 全量连接串与 API Key。

---

## 12. 交叉引用

- 入站字段与头：`docs/api/openclaw-intake.md`  
- 价格外采入库：`openclaw-price-ingest-external`  
- 新闻库治理：`openclaw-public-news-library`  
- 综合发布流程：`openclaw-news-publisher-enhanced`  
- 数据库自检：`scripts/local/verify-openclaw-databases.sh`

---

## 13. 最终回执模板（给用户）

```markdown
已完成价格与新闻联合分析（路径 A / B）。
- monitor_id: …
- 价格窗口: …（列出各 window_days）
- 新闻窗口: …（小时或条数）
- 新闻模式: 多类联合 / single_class_fallback
- horizon: …
- 数据质量: priced_observations=…；新闻有效条数=…；历史报告对照=已做/跳过（原因）
- 情景判断: 上行/下行/震荡；置信度: 高/中/低
- 是否已发布: 是/否；ingest_id: …（若适用）
```
