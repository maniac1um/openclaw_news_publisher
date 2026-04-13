---
name: openclaw-price-ingest-external
description: >
  指导 OpenClaw 在客户端完成价格采集与解析，通过 News Publisher 的 POST observations/ingest 自动入库；
  可选 bootstrap 创建 monitor、GET public/monitoring 校验、external-heartbeat 上报。价格默认以人民币 CNY 计价。
  在用户要求外采价格入库、定时价格上报、服务端不接网页抓取时使用。
---

# OpenClaw 外采价格入库技能（人民币 CNY）

本文档约定：**价格在 OpenClaw 侧抓取或计算**，发布服务 **仅** 通过 HTTP 接收入库，不在服务端对监测 URL 做默认网页抓取。技能为 **自包含说明**：执行前需用户给出 `BASE_URL`、API Key、监测关键词或已有 `monitor_id`。

## 必须遵守的安全准则

每次运行本 skill，均需认真阅读文档内的限制说明。首先，你必须遵守如下的安全限制：

- 当无法确认服务正常运行、或入库/心跳请求持续失败时，不允许盲目重复发送请求；应立刻停止本 skill 的自动重试，向用户报错并附带 HTTP 状态码与响应体摘要（**密钥与 API Key 必须脱敏**）。
- 只有在询问用户是否能发送测试请求并得到用户**明确的肯定回答**后，才能发送测试类请求。测试请求累计**不超过三条**；若需更多次探测，须再次征得用户明确同意。
- 在没有用户明确授权的前提下，不得擅自修改、删除用户仓库或机器上的项目文件；不得为「自行修 bug」而扩大改动范围。仅当用户明确请求协助修复时再介入相关文件。

除上述限制外，下文中的数据质量与合规要求同样不可违反。每次执行前检查是否违反；若发现违反，立刻停止并向用户说明，待用户回复后再继续。

### 数据与网络补充准则

- **禁止编造价格**：`price` 必须来自真实页面、官方接口或用户提供的可验证数值；不得在缺少数据源时填写猜测值。
- **尊重 robots 与站点条款**：采集前评估目标站是否允许自动化访问；遇登录墙、验证码、429 等应停止对该源的自动轰炸并向用户说明。
- **密钥不外泄**：`X-Api-Key` 仅出现在受控环境变量或用户本地配置中，不得写入日志、聊天回执或提交的 `raw_payload` 明文。

---

## 何时使用

在以下场景启用本技能：

- 用户要求 **OpenClaw 执行价格抓取/解析**，服务端 **只做自动接收入库**。
- 用户需要 **定时或事件驱动** 向 `observations/ingest` 上报一条或多条观测。
- 用户已部署 OpenClaw News Publisher，并配置了 **`OPENCLAW_MONITORING_DATABASE_URL`**（默认 **`OPENCLAW_MONITORING_ALLOW_SERVER_SCRAPE=false`**）。

不适用于：坚持要 **服务端 `run-once` 代抓网页** 的场景（应改用主项目 README 中的 legacy 配置说明）。

---

## 价格单位：人民币（CNY）

- **默认且推荐**：所有入库请求的 **`currency` 字段固定为 `"CNY"`**，表示以 **人民币** 为价格单位。
- **原始报价非人民币时**：在 OpenClaw 侧按用户给定汇率或公开牌价 **换算为人民币** 后再写入 `price`，并在 `raw_payload` 中保留原文，例如：`{"original_amount": 74.2, "original_currency": "USD", "fx_note": "用户确认汇率 7.2"}`。
- **若用户书面要求仅保留外币**：仍建议 `currency` 与业务约定一致，并在 `title` 或 `raw_payload` 中明确标注币种，避免门户与报表误读为人民币。

---

## 执行前配置清单（须向用户确认或收集）

执行本技能前，应按下面 **1～4** 逐项补齐；缺任一项且无法合理默认时，应先询问用户，**不得**用猜测值填 `price` 或汇率。

### 1. 服务配置信息

| 项 | 说明 |
|------|------|
| **`BASE_URL`** | 发布服务根 URL，**无尾斜杠**。例：`https://example.com` |
| **`API_KEY`** | 与部署环境变量 **`OPENCLAW_OPENCLAW_API_KEY`** 一致的请求头 **`X-Api-Key`** |

### 2. 监测任务信息（二选一）

| 项 | 说明 |
|------|------|
| **`keyword`** | 监测关键词；**尚无** `monitor_id` 时用于 **`POST .../monitoring/bootstrap`** 创建新任务。例：`黄金价格`、`现货黄金` |
| **或 `monitor_id`** | 已有监测任务 **UUID**；若用户提供此项，**不要**重复 bootstrap，除非用户明确要求新建并行任务 |

二者至少满足其一：无 `monitor_id` 则必须有 `keyword` 以便 bootstrap。

### 3. 黄金价格来源（或任意标的的等价信息）

| 项 | 说明 |
|------|------|
| **数据源 URL** | 实际抓取的页面或 API 地址（例：某行情站「现货黄金」页）。须可合法、可达；若站点禁止自动化访问，应换源或改为用户手动提供数值 |
| **原始价格单位** | 页面上的报价含义须写清，例如：**美元/盎司（USD/troy oz）**、美元/克、人民币/克等。**入库字段仍以 CNY 为主**（见「价格单位」） |
| **汇率 / 换算规则** | 若原始不是人民币：用户须确认 **采用何种汇率或牌价**（例：固定 `USD/CNY=7.2`、某日央行中间价、某 API 实时价）。OpenClaw 在**客户端**完成换算后，**仅将换算后的数值**写入 `price`，并在 **`raw_payload` 中完整保留**：原始数值、原始币种、所用汇率或公式、换算时间，便于审计 |

**盎司 → 人民币（常见思路，须在 `raw_payload` 写明用户认可的公式）**  
国际现货常以 **USD/金衡盎司** 报价。若用户要求入库价为「人民币每盎司」或「人民币每克」等，须在配置清单中固定一种口径，例如：

- 人民币/盎司（金衡）：`(USD_per_oz) × (USDCNY_rate)`  
- 人民币/克：`(USD_per_oz) × (USDCNY_rate) / 31.1034768`（1 金衡盎司 ≈ 31.1034768 克）

**禁止**在未获用户确认的汇率下长期自动「猜汇率」；若用户未给汇率，应 **跳过入库** 或 **仅写入用户当次提供的 CNY 数值**（并在回执中说明未做外汇换算）。

### 4. 定时任务细节

| 项 | 说明 |
|------|------|
| **执行时间** | **立即单次**、还是 **cron 表达式 / 固定间隔**（如每 60 分钟）、或 **指定起始时刻**（如每日 09:00 Asia/Shanghai）。须与用户时区一致 |
| **失败处理** | 与「安全准则」一致：**禁止**对发布服务或数据源无节制重试。用户可选策略示例：`不重试，单次失败则 heartbeat status=error 并停`；`最多 N 次指数退避（N 由用户书面给出）`；`跳过本轮不写库`。**未约定时默认**：失败则 **不** POST ingest，**可** POST external-heartbeat `status=error`，向用户报告，不自动重试 |
| **日志记录** | 建议在 OpenClaw 侧（或 cron 日志）至少保留：**时间、`monitor_id`、数据源 URL、原始报价与单位、所用汇率或「未换算」说明、换算后 CNY `price`、ingest HTTP 状态、`observation_id`（成功时）**。**不得**把 `API_KEY` 写入日志或 `raw_payload` |

**可选（与门户展示相关）**：

- **`job_name`**：`external-heartbeat` 的稳定任务名（例：`openclaw-gold-ingest-hourly`）  
- **是否在每次 ingest 后上报 heartbeat**：由用户决定；若需要首页「外部定时任务」卡片，建议 **成功/失败均上报**

---

## 工作流程

### 1. 健康预检（可选）

- `GET {BASE_URL}/healthz`  
若失败，停止并向用户报告，不要继续 POST 入库。

### 2. 获取 `monitor_id`（尚无则创建）

- **POST** `{BASE_URL}/api/v1/openclaw/monitoring/bootstrap`  
- 请求头：`Content-Type: application/json`、`X-Api-Key: {API_KEY}`  
- 请求体示例：

```json
{
  "keyword": "黄金价格",
  "cadence": "daily",
  "source_profile": "auto"
}
```

（`keyword` 以上文「执行前配置清单」**§2** 为准；非黄金标的则替换为对应关键词。）

保存响应中的 **`monitor_id`**。默认配置下 `inserted_urls` 常为 `1`（占位 URL），属正常现象。

### 3. OpenClaw 侧采集并解析

- 由 OpenClaw（浏览器、脚本或工具链）访问数据源，得到 **数值型** `price`（人民币口径，见上文「价格单位」）。
- 记录可追溯信息：`source_url`、`captured_at`（ISO 8601，建议带时区）、可选 `title`。

### 4. 入库（核心）

- **POST** `{BASE_URL}/api/v1/openclaw/monitoring/{monitor_id}/observations/ingest`  
- 请求头：`Content-Type: application/json`、`X-Api-Key: {API_KEY}`  
- 请求体示例（**人民币默认**）：

```json
{
  "price": 89.9,
  "currency": "CNY",
  "title": "某商城列表页解析",
  "captured_at": "2026-04-10T14:30:00+08:00",
  "source_url": "https://example.com/product/123",
  "raw_payload": {
    "parser": "openclaw-v1",
    "original_amount": 2650.5,
    "original_currency": "USD",
    "original_unit": "per_troy_oz",
    "usdcny_rate": 7.2,
    "fx_note": "用户确认固定汇率，仅作示例",
    "formula": "USD_per_oz * USDCNY → CNY per troy oz"
  }
}
```

（`raw_payload` 按上文「执行前配置清单」**§3** 实际填写；无外汇换算则省略汇率字段并写明原因。）
```

- **`price`**：必填，浮点数。  
- **`currency`**：应 **`"CNY"`**（省略时服务端可能默认 CNY，但本技能要求显式写 `CNY` 以免歧义）。  
- **`captured_at`**：可省略，由服务器时间填充（不推荐长期省略，不利于对齐新闻时间轴）。

成功响应含 **`observation_id`**、**`monitor_url_id`**；失败时读取 HTTP 状态与 JSON `detail`。

### 5. 校验已入库（推荐）

无需 API Key：

- **GET** `{BASE_URL}/api/v1/public/monitoring/{monitor_id}/observations?limit=20`  
- 或 **GET** `{BASE_URL}/api/v1/public/monitoring/{monitor_id}/timeseries?window_days=7`

### 6. 外部定时任务心跳（可选）

若门户需展示「外部 cron / OpenClaw 调度」状态：

- **POST** `{BASE_URL}/api/v1/openclaw/monitoring/external-heartbeat`  
- 请求体示例：

```json
{
  "job_name": "openclaw-price-ingest-hourly",
  "status": "ok",
  "monitor_id": "<monitor_id>",
  "message": "observations ingest completed"
}
```

---

## curl 参考（单条入库）

将占位符替换为实际值：

```bash
curl -sS -X POST "${BASE_URL}/api/v1/openclaw/monitoring/${MONITOR_ID}/observations/ingest" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: ${API_KEY}" \
  -d "{\"price\":89.9,\"currency\":\"CNY\",\"title\":\"sample\",\"source_url\":\"https://example.com/p\"}"
```

---

## 典型错误与处理

| 现象 | 可能原因 | 建议 |
|------|----------|------|
| HTTP 503，detail 含未配置监测库 | 未设置 `OPENCLAW_MONITORING_DATABASE_URL` | 用户配置发布服务环境变量后重试 |
| HTTP 404，Monitor not found | `monitor_id` 错误或服务连错库 | 核对 bootstrap 返回值与部署 |
| HTTP 401 / 403 | API Key 错误 | 核对 `OPENCLAW_OPENCLAW_API_KEY` |
| 入库成功但 observations 为空 | 查错 `monitor_id` 或缓存 | 用 public GET 带正确 id 复查 |

---

## 与用户回执模板

成功：

```markdown
已完成价格入库（人民币 CNY）。
- monitor_id：`…`
- observation_id：`…`
- 数据源：{source_url}
- 抓取/解析时刻：{captured_at}
- 校验：public observations 最新一条与本次一致。
```

失败：

```markdown
价格入库失败（已停止自动重试）。
- 请求：POST .../observations/ingest
- HTTP 状态：…
- 摘要：…（已脱敏）
请用户检查服务配置、网络与 monitor_id。
```

---

## 与其他技能的关系

- **`openclaw-news-publisher-enhanced`**：报告入站与更全的监测 API 索引见该包 §8.6。  
- **`openclaw-price-analysis-reporting`**：在入库后拉取 `summary` / public `observations` 做新闻+价格联合分析。  
- 主项目根目录 **`README.md`**：环境变量与接口权威说明。
