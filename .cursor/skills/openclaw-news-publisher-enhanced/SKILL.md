---
name: openclaw-news-publisher
description: >
  按关键词抓取或整理新闻、生成符合 schema 的报告 JSON，调用 OpenClaw News Publisher 入站 API（POST）并轮询状态；
  价格监测默认由 OpenClaw 侧采集后 POST observations/ingest 入库，服务端不抓网页；可定时 GET public/monitoring 读库。
  可选使用本包内白名单 CLI 与预设种子库发现/维护新闻源。在用户要求爬新闻、出趋势报告并发布到发布服务时使用。
---

# OpenClaw News Publisher Skill（增强包 · 自包含说明）

本文档包含执行本技能所需的全部约定：**不要求阅读本包以外的说明文件**。主流程依赖 `<SKILL_ROOT>/scripts/` 与 `<SKILL_ROOT>/tools/` 下的脚本及 `<SKILL_ROOT>/config/` 下的配置。**OpenClaw 与脚本运行会在技能目录内产生缓存与中间文件**，见 §13。

## 必须遵守的安全准则

每次运行本skill，均需认真阅读文档内的限制说明！首先，你必须遵守如下的安全限制：

- 当无法接收到发布成功，服务器正常运行的反馈时，不允许再次发送或是私自发送测试请求，立刻停止运行skill，并直接向用户报错，附带网站输出的报错信息。
- 在上一条的基础上，只有在询问用户是否能发送测试请求并得到用户明确的肯定回答后，才能发送测试信息。注意！你仅仅只能发送有限的，不超过三条的测试信息，若需要发送更多的测试信息，需要再次询问获得用户的明确同意。
- 在上两条的基础上，你没有任何权限自主对用户已有的项目文件进行修改与添加。如非必要不选择自主修复bug。只有当用户明确表达帮忙修复问题时才能介入。

除了如上的安全限制，下文也有许多需要你注意的限制。这些限制同样不可违反！绝对不能违反这些限制，每次运行都需要检查是否违反这些限制，随时检查是否违反。如果发现违反，立刻停止服务并向用户说明情况！待用户回复之后才能重新开始。

---

## 文档导航（按需跳转）

| 章节 | 内容 |
|------|------|
| §1 | 技能根目录与包内文件清单 |
| §2 | 何时使用 |
| §3 | 环境与依赖 |
| §4 | 端到端主流程与路径分支 |
| §5 | POST 报告 JSON 字段与爬虫输出注意点 |
| §6 | `news_crawler.py` 行为、参数、配置文件 |
| §7 | 白名单 CLI、`seed_urls.json`、`whitelist.json` |
| §8 | 发布服务 & 监测服务 HTTP 接口与典型错误 |
| §9–§12 | 幂等、质量、限制、用户回执模板 |
| §13 | 技能目录内运行时文件与 OpenClaw 缓存 |

---

## 1. 技能根目录与包内文件

**技能根目录**：与本 `SKILL.md` **同级**的目录，记为 `<SKILL_ROOT>`。所有相对路径均相对该目录；执行命令前应先 `cd "<SKILL_ROOT>"`。

**本包实际包含**（勿假设存在未列出的脚本）：

| 路径 | 用途 |
|------|------|
| `scripts/news_crawler.py` | 基于标准库的 HTTP 爬虫，输出报告 JSON |
| `scripts/crawler_config.example.json` | 爬虫 JSON 配置字段示例 |
| `tools/cli.py` | 白名单与发现流程的 CLI 入口（`asyncio` + `aiohttp`）；含 `cleanup` 子命令 |
| `tools/skill_cleanup.py` | **任务结束后清理**技能根目录内临时文件（见 §13） |
| `tools/core/whitelist_manager.py` | 读写 `whitelist.json`、批量测 URL、清理失败源 |
| `tools/core/first_run_discovery.py` | 读 `seed_urls.json` 生成候选 URL 并探测 |
| `tools/core/dynamic_maintenance.py` | 每日维护、快速测试、`suggest` 推荐逻辑 |
| `config/whitelist.json` | 活跃源、历史、统计、可调参数 |
| `config/seed_urls.json` | 预设种子库 + `discovery_strategy`（§7.1） |
| `requirements.txt` | 依赖：`aiohttp>=3.9.0`（CLI 必需；仅跑爬虫时可不装） |

---

## 2. 何时使用本技能

- 用户要按 **关键词** 抓取/汇总新闻并生成 **结构化报告**，且要提交到 **发布服务**。
- 用户明确要调用 `POST /api/v1/openclaw/reports` 或「发布到门户 / 新闻动态」。
- 用户要做“价格监测/趋势”（不是新闻报道），并使用监测接口（见 §8.6）。
- 需要 **发现、测试、维护** 可访问的新闻首页 URL（白名单 + 种子库）。

若用户只要一段分析文字、**不**调用发布接口，不必走 POST 流程。

---

## 3. 环境与依赖

```bash
cd "<SKILL_ROOT>"
python3 -m pip install -r requirements.txt
```

- **Python**：建议 3.11+（与爬虫类型注解一致）。
- **`tools/cli.py`**：必须能 `import aiohttp`。
- **`scripts/news_crawler.py`**：主要使用标准库；**不依赖** aiohttp。

---

## 4. 端到端主流程与路径分支

### 4.1 三条常见路径（选一条走通）

**路径 A — 用户已给出可爬的首页/栏目 URL**

1. 直接用 §6 `news_crawler.py`（`--urls` 或 `--urls-file` 或 `--config` 中带 `seed_urls`）。
2. 编辑产出 JSON（§5.1 必做项）。
3. §8 POST → 轮询 → §12 回执。

**路径 B — 需要先积累白名单 URL**

1. §7 `tools/cli.py init` 或 `discover` / `refresh`（读 `seed_urls.json`，写 `whitelist.json`）。
2. `list` 或 `suggest` 得到若干 `https://...` 根地址。
3. 将 URL 作为 §6 的 seed，跑爬虫 → §5.1 → §8。

**路径 C — 已有符合 §5 的 JSON**

1. 仅校验字段与合规 → §8 POST → 轮询 → §12。

### 4.2 逐步清单（与路径无关的后半段）

1. **收集**：`BASE_URL`（如 `http://127.0.0.1:8000`，无尾斜杠）、`X-Api-Key`、用户 `keyword`、业务 `task_id`、时间范围（写入 `time_range`）。
2. **生成 JSON**：路径 A/B/C 之一；**不得**伪造不存在的原文 `url`。
3. **提交前修正**（§5.1）：爬虫会生成自己的 `task_id` 与占位 `analysis`/`generated_title`，若与用户任务不一致，**必须在 POST 前改好**。
4. **新任务幂等**：生成新的 `X-Request-Id`；与 `task_id` 一起记录。同一任务网络重试时二者**均不变**。
5. **POST**：`POST {BASE_URL}/api/v1/openclaw/reports`，记录 `ingest_id`。
6. **轮询**：`GET {BASE_URL}/api/v1/openclaw/reports/{ingest_id}`，间隔 1–3s，直到 `published` 或 `failed`（建议总超时 60–300s，视部署而定）。
7. **回执**：§12；失败附 HTTP 状态与 body 摘要（密钥脱敏）。
8. **清理磁盘（推荐必做，尤其小盘环境）**：在步骤 7 已完成、且**无需保留本次中间 JSON** 时，立即执行 §13 的 `skill_cleanup.py`（可选用 `--prune-whitelist-history` 收缩 `whitelist.json` 内历史日志）。

**可选预检**：`GET {BASE_URL}/healthz`、`GET {BASE_URL}/healthz/db`。

---

## 5. 报告 JSON（POST 请求体）

### 5.1 与服务端 schema 对齐的字段

服务端模型要求以下字段均有有效值（见发布服务实现中的 `OpenClawReportIn`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 非空；业务任务 ID |
| `keyword` | string | 非空 |
| `time_range` | object | `start`、`end` 为 ISO 8601 时间 |
| `sources` | string[] | 来源标识列表，与 `items` 可追溯 |
| `items` | array | 每项含 `title`、`source`、`url`、`published_at`（ISO）；可选 `price`、`currency`、`summary` |
| `analysis` | string | 非空；应有归纳结论，不能只有模板句 |
| `generated_title` | string | 非空；面向用户的标题 |
| `generated_at` | string | ISO 8601 |

### 5.2 使用 `news_crawler.py` 后必须检查

脚本写出的 JSON 中：

- `task_id` 固定为 `crawl-` + 随机 hex（**若用户需要固定业务 ID，POST 前替换为你的 `task_id`**）。
- `time_range`：由 `--hours-back` 与抓取结束时刻推算；若与用户要求不符，应改。
- `analysis` / `generated_title`：为**占位**性质，通常需按用户意图重写。
- `items` 可能为空：若为空，一般**不应**强行 POST（除非用户接受空报告）；应换 URL、放宽 `max_pages`/`max_items` 或换源。

示例结构（字段名对齐即可）：

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

---

## 6. 通用爬虫 `scripts/news_crawler.py`

### 6.1 能力边界

- 使用 `urllib` 拉取 HTML，**不执行 JavaScript**；SPA、强登录、强反爬站点可能拿不到正文。
- 从 seed 出发 **BFS**：队列扩展同站内链接；仅保留 `include_domains` 内域名；跳过含 `deny_url_keywords` 的 URL。
- **文章页启发式**：路径含 `/news/`、`/article/` 等，或含 `/yyyy/mm/dd/` 时更可能当作文章解析；从 meta/`h1`/首段抽取标题、摘要、时间。
- **终止条件**：已抓取页数达 `max_pages`，或已收集条目数达 `max_items`，或队列为空。

### 6.2 命令行参数（完整）

| 参数 | 说明 |
|------|------|
| `--keyword` | **必填**，写入报告 `keyword` |
| `--urls` | 可选，多个 seed URL |
| `--urls-file` | 可选，每行一个 URL，`#` 开头为注释 |
| `--config` | 可选，JSON 配置文件路径 |
| `--hours-back` | 默认 `72`；`>0` 时按发布时间过滤条目；`0` 表示不启用时间下限 |
| `--max-pages` | 默认 30；**命令行优先于**配置文件中的 `max_pages`（若 CLI 使用默认值则配置文件可覆盖，见 §6.3） |
| `--max-items` | 默认 20；同上 |
| `--output` | 输出 JSON 路径，默认 `report_payload.json`；**建议**写到 `runs/xxx.json`（需先 `mkdir -p runs`），便于与 §13 一次性清理 |

**必须至少有一种 seed 来源**：`--config` 中的 `seed_urls`、`--urls`、`--urls-file` 之一非空；否则脚本报错 `No seed URLs provided`。

### 6.3 配置文件字段（与 `crawler_config.example.json` 一致）

| 字段 | 说明 |
|------|------|
| `seed_urls` | 字符串数组，起始 URL |
| `include_domains` | 允许爬取的注册域名（小写主机名）；**若省略或空数组**，脚本会用所有 seed 的域名**自动推导** |
| `max_pages` / `max_items` | 上限；与 CLI 的合并规则见下 |
| `timeout_seconds` / `retries` / `backoff_base_seconds` | 请求超时、重试次数、指数退避基数 |
| `delay_range_seconds` | `[min, max]` 秒，每页抓取后随机 sleep |
| `deny_url_keywords` | URL 子串黑名单 |

**`max_pages` / `max_items` 合并规则**（源码逻辑）：  
`int(args.max_pages or config_json.get("max_pages") or DEFAULT)` —— 因 argparse 默认值总是非空，**命令行传入的默认 30/20 会覆盖配置文件**；若要用配置文件里的数值，需在命令行显式传入与期望一致的 `--max-pages` / `--max-items`，或修改脚本调用方式（执行者需知晓此行为）。

### 6.4 命令示例

```bash
cd "<SKILL_ROOT>"
python3 scripts/news_crawler.py \
  --keyword "羽毛球" \
  --urls "https://example.com/news" "https://example.com/industry" \
  --max-pages 40 \
  --max-items 20 \
  --hours-back 168 \
  --output report_payload.json
```

```bash
cd "<SKILL_ROOT>"
python3 scripts/news_crawler.py \
  --keyword "羽毛球" \
  --config scripts/crawler_config.example.json \
  --output report_payload.json
```

---

## 7. 白名单 CLI、`seed_urls.json` 与 `whitelist.json`

### 7.1 预设种子库 `config/seed_urls.json`

**用途**：供 `FirstRunDiscovery` 在 **`init` / `discover` / `refresh` 内嵌的发现步骤** 中读取，**不**被 `news_crawler.py` 直接读取。

**`categories`（按分类）**：

- `url_patterns`：含 `{domain}` 的模板字符串。
- `domains`：与模板拼成候选根 URL。
- `keywords`：**英文**关键词列表；`init`/`discover` 传入的用户词会与这些词做**子串匹配**（`kw in user_keyword.lower()`）以选择分类。若用户只给中文、且与英文关键词无交集，可能**匹配不到分类**，导致发现数量偏少——宜在 `init --keywords` 中同时传入如 `sports`、`news` 等与种子库一致的行业英文词，或由维护者扩充 `keywords`。

**`discovery_strategy`（可选，与代码中读取一致）**：

- `initial_test_count`、`max_concurrent_tests`、`test_timeout_seconds`、`min_success_for_addition` 等：控制首轮测试规模、并发、超时与加入白名单的阈值。
- `domain_variations`：域名变体模式（用于部分发现逻辑）。

若文件缺失或 JSON 损坏，发现模块会回退到内置极简 `general` 域名列表（见 `first_run_discovery.py`）。

### 7.2 白名单文件 `config/whitelist.json`

**顶层字段**：

| 字段 | 说明 |
|------|------|
| `version` | 配置版本号 |
| `created_at` / `last_updated` / `last_full_test` | 时间戳 |
| `config` | 可调参数（见下表） |
| `active` | 对象：**键为分类名**，值为该分类下新闻源对象数组 |
| `history` | 如 `removed`、`test_log` |
| `statistics` | 聚合统计 |
| `user_preferences` | 如 `frequent_keywords`（`refresh` 发现新源时可能使用） |

**`config` 中常见键**（以当前文件为准，可用 `python3 tools/cli.py config --show` 查看）：

| 键 | 含义 |
|----|------|
| `test_concurrency` | 批量测试并发度 |
| `test_timeout_seconds` | 单次 HTTP 测试超时 |
| `cache_ttl_seconds` | 测试结果缓存 TTL |
| `failure_threshold` | 失败次数阈值（与清理逻辑相关） |
| `min_success_rate` | 低于则可能被清理 |
| `auto_discovery_enabled` | 是否允许自动发现 |
| `daily_test_enabled` | 是否启用每日维护中的测试 |

**`active[分类][]` 中每条源**常见字段：`url`、`title`、`description`、`added_at`、`last_tested`、`success_count`、`failure_count`、`success_rate`、`last_response_time_ms`、`usage_count`、`keywords`。

### 7.3 `tools/cli.py` 子命令说明

**工作目录**：必须在 `<SKILL_ROOT>`，以便相对路径 `config/whitelist.json`、`config/seed_urls.json` 正确。

**非交互自动化**：`init` 使用 `--skip-prompt`、`--skip-confirm`，避免 `input()` 阻塞。

| 命令 | 作用 | 重要参数 |
|------|------|----------|
| `init` | 按关键词做首次发现，探测 URL 并写入白名单 | `--keywords`、`--skip-prompt`、`--skip-confirm` |
| `test` | 测活跃源 | `--all` 全量；或 `--quick` 快速（维护模块） |
| `discover` | 再跑一轮发现 | `--keywords`；`--limit` 在 argparse 中定义，**当前实现未传入发现逻辑**，不要依赖其截断效果 |
| `add` | 手动添加 URL；会先 `aiohttp` 探测，成功才写入 | `--url`、`--category`（默认 `general`） |
| `remove` | 按精确 URL 从 `active` 移除并记入 `history.removed` | `--url` |
| `list` | 打印分类统计或某分类下的 URL | `--category` 可选 |
| `stats` | 打印统计摘要 | 无 |
| `refresh` | `test_all` → 清理失败源 → 若活跃源总数 < 15 或 `--force-discover` 则再发现 | `--force-discover` |
| `daily` | 走 `DynamicMaintenance.run_daily_maintenance()` | 无 |
| `suggest` | 按关键词从白名单推荐 URL | `--keyword` |
| `config` | 查看或设置 `whitelist.json` 内 `config` 键 | `--show` 或 `--set key value` |
| `cleanup` | 调用 `skill_cleanup.py` 清理临时文件 | `--dry-run`、`--prune-whitelist-history` |

**与爬虫衔接**：从 `list` / `suggest` 输出中复制根 URL，作为 `news_crawler.py --urls ...` 的 seed（必要时多传几个栏目首页）。

**任务结束后释放空间**（与 §4 步骤 8 一致）：

```bash
cd "<SKILL_ROOT>"
python3 tools/skill_cleanup.py
# 若 whitelist 的 history 体积过大且无需保留移除/测试日志：
python3 tools/skill_cleanup.py --prune-whitelist-history
# 或：
python3 tools/cli.py cleanup
python3 tools/cli.py cleanup --prune-whitelist-history
```

```bash
cd "<SKILL_ROOT>"
python3 tools/cli.py init --keywords sports badminton --skip-prompt --skip-confirm
python3 tools/cli.py suggest --keyword badminton
python3 tools/cli.py test --quick
python3 tools/cli.py refresh --force-discover
```

---

## 8. 发布服务 HTTP 接口

**前缀**：以下路径均相对于 `{BASE_URL}`（已含 `/api/v1` 的部署以实际为准；开源默认入站在 `/api/v1/openclaw/...`）。

### 8.1 提交报告

- **POST** `{BASE_URL}/api/v1/openclaw/reports`
- **成功**：HTTP **202**，JSON 含 `ingest_id`、`status`（常见初始为 `queued`）。
- **请求头**：
  - `Content-Type: application/json`
  - `X-Api-Key: <与部署 OPENCLAW_OPENCLAW_API_KEY 一致>`
  - `X-Request-Id: <幂等键>`（可与 `task_id` 同值或独立 UUID，但必须符合 §9）
- **可选**：若开启签名校验，需按部署增加 `X-Signature`（请求体 HMAC，见服务实现）。

```bash
curl -sS -X POST "${BASE_URL}/api/v1/openclaw/reports" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: ${API_KEY}" \
  -H "X-Request-Id: ${REQUEST_ID}" \
  --data-binary @report_payload.json
```

### 8.2 查询入站状态（轮询）

- **GET** `{BASE_URL}/api/v1/openclaw/reports/{ingest_id}`
- **响应字段**（典型）：`ingest_id`、`request_id`、`task_id`、`status`（`queued` / `processing` / `published` / `failed`）、`raw_path`、`rendered_path`、`error`（失败时）。
- **404**：`ingest_id` 不存在。
- **401**：API Key 错误。

### 8.3 门户列表与详情（用户侧）

- `GET {BASE_URL}/api/v1/public/reports`
- `GET {BASE_URL}/api/v1/public/reports/{ingest_id}`

部分部署在**未配置数据库**或策略为「仅库表」时，可能返回 **503** 或空列表；以实际响应为准。

### 8.4 批量删除（仅当用户明确要求）

- **POST** `{BASE_URL}/api/v1/public/reports/bulk-delete`
- **体**：`{ "ingest_ids": ["uuid", ...] }`
- **响应**：含 `requested`、`deleted`、`not_found` 计数；持久化是否同步删文件取决于服务端版本。

### 8.5 预留：失败重试接口

- `POST {BASE_URL}/api/v1/openclaw/reports/{ingest_id}/retry` 在参考实现中可能返回 **501**；不要依赖其实现，失败时优先联系用户或修正 JSON 后**新任务**重提。

### 8.6 价格监测 HTTP 接口（默认：OpenClaw 采集，服务端入库）

**前缀**：以下路径均相对于 `{BASE_URL}`（已含 `/api/v1` 的部署以实际为准）。

**前置条件**：
- 部署需配置 `OPENCLAW_MONITORING_DATABASE_URL`，用于 `price_monitors / price_monitor_urls / price_observations`。
- 写入类接口（除 **public** GET 外）：请求头 `X-Api-Key: <与部署 OPENCLAW_OPENCLAW_API_KEY 一致>`。

**环境变量（必读）**：
- **`OPENCLAW_MONITORING_ALLOW_SERVER_SCRAPE`**（默认 `false`）：为 `false` 时，服务端 **不对** 监测 URL 做公网 HTTP 抓取；`bootstrap` 仅建任务 + 一条占位 URL；价格由 OpenClaw **`POST .../observations/ingest`** 写入。设为 `true` 可恢复旧版：`bootstrap` 生成多条候选 URL，且 **`run-once`** 会抓取页面。
- **`OPENCLAW_MONITORING_SCHEDULER_ENABLED`**：进程内定时器只会调用 `run-once`；在默认 `ALLOW_SERVER_SCRAPE=false` 时 **不会启动**（即使 enabled=true）。需要 legacy 服务端抓取时须同时 `ALLOW_SERVER_SCRAPE=true`。

#### 8.6.1 创建监测任务（bootstrap）

- **POST** `{BASE_URL}/api/v1/openclaw/monitoring/bootstrap`

默认模式下请求体仍可带 `candidate_count` / `platforms` / `source_profile`，但 **不会** 用于生成大量抓取 URL（仅保留关键词、`cadence` 等）。

```json
{
  "keyword":"羽毛球价格",
  "candidate_count":20,
  "platforms":["taobao","tmall","jd","news"],
  "cadence":"daily"
}
```

#### 8.6.2 上报一条价格观测（主路径，推荐）

- **POST** `{BASE_URL}/api/v1/openclaw/monitoring/{monitor_id}/observations/ingest`

```json
{
  "price": 523.4,
  "title": "可选，页面或数据源说明",
  "currency": "CNY",
  "captured_at": "2026-04-10T12:00:00+08:00",
  "source_url": "https://example.com/quote",
  "raw_payload": { "vendor": "example" }
}
```

```bash
curl -sS -X POST "$BASE_URL/api/v1/openclaw/monitoring/<monitor_id>/observations/ingest" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: ${API_KEY}" \
  -d '{"price":89.9,"currency":"CNY","title":"sample","source_url":"https://example.com/p"}'
```

#### 8.6.3 公开读库（OpenClaw 定时拉取，无需 API Key）

用于生成报告前读取已入库数据：

- **GET** `{BASE_URL}/api/v1/public/monitoring/monitors`
- **GET** `{BASE_URL}/api/v1/public/monitoring/{monitor_id}/timeseries?window_days=30`
- **GET** `{BASE_URL}/api/v1/public/monitoring/{monitor_id}/observations?limit=200`

```bash
curl -sS "$BASE_URL/api/v1/public/monitoring/<monitor_id>/observations?limit=100"
```

#### 8.6.4 查询最近窗口期摘要（需 API Key）

- **GET** `{BASE_URL}/api/v1/openclaw/monitoring/{monitor_id}/summary?window_days=7`

```bash
curl -sS "$BASE_URL/api/v1/openclaw/monitoring/<monitor_id>/summary?window_days=7" \
  -H "X-Api-Key: ${API_KEY}"
```

#### 8.6.5 可选：追加参考 URL

- **POST** `{BASE_URL}/api/v1/openclaw/monitoring/{monitor_id}/urls`

仅在 **`OPENCLAW_MONITORING_ALLOW_SERVER_SCRAPE=true`** 时，`run-once` 才会对这些 URL 做服务端抓取；默认模式下追加 URL 不影响 **ingest** 主路径（ingest 使用占位 `monitor_url_id`）。

```json
{
  "platform":"jd",
  "urls":[
    "https://example.com/product/123"
  ]
}
```

#### 8.6.6 执行一次服务端网页采样（legacy，可选）

- **POST** `{BASE_URL}/api/v1/openclaw/monitoring/{monitor_id}/run-once`

默认响应含 **`server_scrape_skipped: true`**，不发起外网请求。仅当 **`OPENCLAW_MONITORING_ALLOW_SERVER_SCRAPE=true`** 且存在可抓外部链时才会抓取。

```bash
curl -sS -X POST "$BASE_URL/api/v1/openclaw/monitoring/<monitor_id>/run-once" \
  -H "X-Api-Key: ${API_KEY}"
```

**质量说明（legacy 抓取）**：
- `run-once` 为纯 HTTP（不执行 JavaScript），启发式抽价；动态站可能 `priced_observations` 为 0。

#### 8.6.7 内部定时任务（仅 legacy 服务端抓取）

当你需要进程内周期 **抓取**（非默认）时，须同时：

```bash
export OPENCLAW_MONITORING_DATABASE_URL='postgresql://openclaw_monitor:<请替换密码>@127.0.0.1:5432/openclaw_monitor'
export OPENCLAW_MONITORING_ALLOW_SERVER_SCRAPE='true'
export OPENCLAW_MONITORING_SCHEDULER_ENABLED='true'
export OPENCLAW_MONITORING_SCHEDULER_MONITOR_ID='<monitor_id>'
export OPENCLAW_MONITORING_SCHEDULER_INTERVAL_MINUTES='60'
export OPENCLAW_MONITORING_SCHEDULER_RUN_ON_START='true'
```

状态查询：

- **GET** `{BASE_URL}/api/v1/openclaw/monitoring/scheduler/status`（响应含 `allow_server_scrape`）

```bash
curl -sS "$BASE_URL/api/v1/openclaw/monitoring/scheduler/status" \
  -H "X-Api-Key: ${API_KEY}"
```

#### 8.6.8 外部 cron/scheduler 心跳上报（门户可视化）

当采用外部调度器（Linux `cron` / K8s CronJob 等）执行 **采集 + ingest** 时，推荐在每次任务结束后上报心跳。

- **POST** `{BASE_URL}/api/v1/openclaw/monitoring/external-heartbeat`
- **请求体字段**：`job_name`、`status`（`ok`/`error`）、可选 `monitor_id`、`message`

```bash
curl -sS -X POST "$BASE_URL/api/v1/openclaw/monitoring/external-heartbeat" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: ${API_KEY}" \
  -d '{
    "job_name":"openclaw-price-ingest-hourly",
    "status":"ok",
    "monitor_id":"9551be2b-3e27-4935-a595-d1699163a3e9",
    "message":"observations ingest completed"
  }'
```

公开查询：

- **GET** `{BASE_URL}/api/v1/public/monitoring/external-jobs`

```bash
curl -sS "$BASE_URL/api/v1/public/monitoring/external-jobs"
```

建议流程（**默认**，外部调度）：
1. OpenClaw 侧完成页面拉取与价格解析。
2. **`POST /monitoring/{monitor_id}/observations/ingest`** 写入观测。
3. 成功/失败后 **`POST /monitoring/external-heartbeat`**。
4. 需要生成报告时，**`GET /public/monitoring/...`** 拉已存数据，再按需 **`POST /openclaw/reports`**。

---

## 9. 幂等与重试

- **新任务**：新 `X-Request-Id` + 新 `task_id`。
- **同一任务**因网络中断重发 POST：**相同** `X-Request-Id` + **相同** `task_id`。
- **禁止**用新幂等键伪装成「同一任务」以免产生重复入库（行为依赖服务端实现）。

---

## 10. 质量与合规

- `sources` 与 `items[*].source`、`url` 一致可追溯。
- 时间字段 ISO 8601。
- `analysis` 必须有推理或归纳，不得仅堆标题。
- 无法合法获取网页时，向用户说明；**禁止编造可点击的假新闻 URL**。

---

## 11. 限制说明（执行预期）

- 纯 HTTP 爬虫对 **JS 渲染站、登录墙、验证码** 无效。
- 白名单发现依赖 **外网 HTTP 可达**；部分国际站点在特定网络环境下可能全失败。
- **自动发现 ≠ 一定能爬出正文**：入白名单仅表示根 URL 探测通过，正文抽取仍受 §6.1 限制。

---

## 12. 执行结束后对用户的回执模板

成功或处理中：

```markdown
已提交报告：{generated_title}
- 关键词：{keyword}，时间范围：{time_range.start} ~ {time_range.end}
- ingest_id: {ingest_id}
- 当前状态：{queued|processing|published|failed}
```

失败：

```markdown
提交或处理失败
- ingest_id（若有）：{ingest_id}
- 摘要：{HTTP 状态码或错误信息}
```

---

## 13. 技能目录内的运行时文件、OpenClaw 缓存与**每次调用后清理**

在实际使用中，**OpenClaw（或承载技能的运行时）往往会把技能包所在目录当作工作区**，向 `<SKILL_ROOT>` 内持续写入各类文件。这与「随包分发的静态脚本/配置」不同，容易造成**目录下出现大量缓存、中间产物或重复输出**。在**磁盘或内存紧张**的环境下，应在**单次任务闭环结束后**（§4 步骤 7 回执完成之后）**例行执行清理**，除非用户明确要求保留中间文件。

### 13.1 官方清理工具：`tools/skill_cleanup.py`

**用途**：在技能根目录内删除**可再生成**的临时内容，减小占用。

**默认会删除或清空**（路径均相对 `<SKILL_ROOT>`）：

| 目标 | 说明 |
|------|------|
| `report_payload.json` | 爬虫默认输出 |
| `runs/` 下所有文件 | 若存在该目录，删除其中文件后尝试删除空目录 |
| `.openclaw/` | 若存在（常见于 OpenClaw 在技能副本下写入缓存） |
| `tools/__pycache__`、`tools/core/__pycache__`、`scripts/__pycache__` | Python 字节码缓存 |
| 根目录下若干示例性报告 JSON | 如 `gold_price_report.json`、`badminton_price_report.json`（若存在） |

**不会删除**：`SKILL.md`、`scripts/` 与 `tools/` 内源码、`config/seed_urls.json`、以及**默认情况下**完整的 `config/whitelist.json`（其中 **活跃新闻源 `active` 会保留**）。

**可选参数**：

- `--dry-run`：只打印将处理的路径，不删除。
- `--prune-whitelist-history`：将 `config/whitelist.json` 中的 `history.test_log` 与 `history.removed` **清空为 `[]`**，用于抑制日志型字段无限膨胀；**不删除** `active` 中的源。

**调用示例**：

```bash
cd "<SKILL_ROOT>"
python3 tools/skill_cleanup.py
python3 tools/skill_cleanup.py --prune-whitelist-history
python3 tools/cli.py cleanup --dry-run
```

### 13.2 常见来源（非穷举）

| 来源 | 可能出现的内容 |
|------|----------------|
| **OpenClaw / 代理运行时** | 会话或任务中间态、重复保存的 JSON、调试 dump 等；部分环境写入 `<SKILL_ROOT>/.openclaw/`（已由 §13.1 默认清理覆盖）。 |
| **`news_crawler.py`** | `--output` 指向的文件；建议使用 `runs/` 子目录集中存放，与清理脚本一致。 |
| **`tools/cli.py` 与白名单** | `config/whitelist.json` 随 `history.*` 变长；用 `--prune-whitelist-history` 瘦身。 |
| **进程内** | `whitelist_manager.test_cache` 仅内存，进程结束即释放。 |

### 13.3 与安全准则的关系

- 用户**主动提出**要省空间、且任务已结束时，执行 §13.1 **不违反**「不得擅自删用户文件」的意图：清理脚本**只针对本技能包内约定的临时路径**，不扫删用户仓库其他目录。
- 若用户**明确要求保留**某次 `report_payload.json` 供复查，则**跳过**清理或改用 `--dry-run` 确认后再决定。
- **勿手动删除**整个 `config/whitelist.json`** 除非用户确认放弃白名单**；需要减负时优先 `--prune-whitelist-history`。

### 13.4 版本管理建议

若技能目录在 Git 仓库内，可在仓库 `.gitignore` 中加入：`runs/`、`report_payload.json`、`.openclaw/` 等（以实际落盘为准）。

### 13.5 与 API 契约的关系

本节不改变 §8；仅规范**本地磁盘**侧行为。

---

**文档版本**：增强包自包含版（扩写说明与实现细节对齐）。**勿引用本 SKILL 未列出的脚本名。**
