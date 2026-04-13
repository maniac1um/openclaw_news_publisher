# OpenClaw News Publisher Enhanced

增强版的OpenClaw新闻发布skill，具备智能白名单管理和自动发现功能。

## 特性

### 🚀 开箱即用
- **首次运行自动发现**：无需手动配置，自动寻找可用新闻源
- **智能关键词匹配**：根据用户领域倾向优化新闻源选择
- **零配置启动**：用户只需提供关键词，skill自动完成配置

### 🔄 动态维护
- **每日自动测试**：保持白名单的时效性和可靠性
- **智能清理机制**：自动移除失败率过高的新闻源
- **新源自动发现**：根据用户使用模式发现相关新源
- **用户偏好学习**：随使用时间优化白名单质量

### ⚡ 高效性能
- **并行测试**：支持最多10个并发测试，提高效率
- **智能缓存**：测试结果缓存，避免重复测试
- **分层策略**：按使用频率优化测试优先级
- **增量更新**：只测试需要更新的部分

### 🛠️ 完全可控
- **完整命令行接口**：提供所有功能的命令行控制
- **可配置参数**：所有自动功能都可调整或禁用
- **详细统计信息**：完整的测试和维护报告
- **手动控制**：支持手动添加/移除/测试新闻源

## 快速开始

### 安装依赖
```bash
pip install aiohttp
```

### 首次运行
```bash
# 使用关键词初始化
python tools/cli.py init --keywords "sports badminton"

# 或使用交互模式
python tools/cli.py init
```

### 基本使用
```bash
# 查看白名单
python tools/cli.py list

# 测试所有新闻源
python tools/cli.py test --all

# 刷新白名单（测试+清理+发现）
python tools/cli.py refresh

# 查看统计信息
python tools/cli.py stats
```

## 在 OpenClaw 内快速启用价格监测定时任务

如果你已经在主项目中创建了 `monitor_id`，可以直接启用 OpenClaw 内置 scheduler（不需要 cron/systemd）：

```bash
export OPENCLAW_MONITORING_DATABASE_URL='postgresql://openclaw_monitor:<请替换密码>@127.0.0.1:5432/openclaw_monitor'
export OPENCLAW_MONITORING_SCHEDULER_ENABLED='true'
export OPENCLAW_MONITORING_SCHEDULER_MONITOR_ID='<monitor_id>'
export OPENCLAW_MONITORING_SCHEDULER_INTERVAL_MINUTES='60'
export OPENCLAW_MONITORING_SCHEDULER_RUN_ON_START='true'
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

验证 scheduler 状态：

```bash
curl -sS "http://127.0.0.1:8000/api/v1/openclaw/monitoring/scheduler/status" \
  -H "X-Api-Key: dev-openclaw-key"
```

## 目录结构

```
openclaw-news-publisher-enhanced/
├── README.md                    # 本文档
├── SKILL.md                     # OpenClaw skill文档
├── requirements.txt             # Python依赖
├── config/
│   ├── whitelist.json          # 统一白名单配置
│   └── seed_urls.json          # 预设种子库
├── scripts/
│   ├── news_crawler.py         # 新闻爬虫
│   └── crawler_config.example.json
└── tools/
    ├── cli.py                  # 命令行接口
    └── core/
        ├── whitelist_manager.py    # 白名单管理核心
        ├── first_run_discovery.py  # 首次运行发现
        └── dynamic_maintenance.py  # 动态维护
```

## 核心功能

### 1. 首次运行自动发现
当skill首次运行时，自动执行：
- 分析用户关键词，确定领域倾向
- 从预设种子库生成测试URL
- 并行测试URL可访问性
- 自动分类并加入白名单
- 生成完整的初始配置

### 2. 动态白名单维护
**每日自动执行**：
- 测试所有活跃新闻源连通性
- 移除连续失败率过高的源
- 检查活跃源数量，不足时自动发现新源
- 更新用户使用偏好统计

**手动控制命令**：
```bash
# 运行每日维护
python tools/cli.py daily

# 快速测试（最近使用/高成功率）
python tools/cli.py test --quick

# 发现新源
python tools/cli.py discover --keywords technology --limit 5
```

### 3. 统一配置管理
所有配置集中存储在 `config/whitelist.json`：
```json
{
  "active": { ... },      # 活跃新闻源
  "history": { ... },     # 历史记录
  "statistics": { ... },  # 统计信息
  "user_preferences": { ... },  # 用户偏好
  "config": {             # 可配置参数
    "test_concurrency": 10,
    "daily_test_enabled": true,
    "auto_discovery_enabled": true
  }
}
```

### 4. 命令行工具
完整的命令行接口支持所有操作：

```bash
# URL管理
python tools/cli.py add --url https://example.com --category news
python tools/cli.py remove --url https://example.com
python tools/cli.py list --category sports

# 测试与发现
python tools/cli.py test --all
python tools/cli.py discover --keywords finance

# 维护与统计
python tools/cli.py refresh
python tools/cli.py daily
python tools/cli.py stats
python tools/cli.py suggest --keyword sports

# 配置管理
python tools/cli.py config --show
python tools/cli.py config --set test_concurrency 5
```

## 预设种子库

`config/seed_urls.json` 包含预设的新闻源分类：

- **sports**：体育新闻（ESPN, SkySports, SportingNews等）
- **news**：综合新闻（CNN, BBC, Reuters, AP News等）
- **tech**：科技新闻（TechCrunch, The Verge, Wired等）
- **finance**：财经新闻（Bloomberg, WSJ, FT等）
- **entertainment**：娱乐新闻（Variety, Hollywood Reporter等）

每个分类包含：
- 域名列表
- URL模式
- 关键词映射
- 发现策略

## 集成到OpenClaw

在OpenClaw skill中集成白名单管理：

```python
# 检查是否需要首次运行
if is_first_run():
    run_first_discovery(user_keywords)

# 检查是否需要每日维护
if should_run_daily_test():
    run_daily_maintenance()

# 获取推荐的新闻源
sources = get_recommended_sources(keyword)
```

## 配置选项

### 主要配置参数
```json
{
  "test_concurrency": 10,          # 并发测试数量
  "test_timeout_seconds": 5,       # 单次测试超时
  "cache_ttl_seconds": 3600,       # 缓存有效期
  "failure_threshold": 3,          # 失败阈值
  "min_success_rate": 0.7,         # 最低成功率
  "auto_discovery_enabled": true,  # 自动发现开关
  "daily_test_enabled": true       # 每日测试开关
}
```

### 修改配置
```bash
# 查看当前配置
python tools/cli.py config --show

# 修改配置
python tools/cli.py config --set test_concurrency 5
python tools/cli.py config --set auto_discovery_enabled false
```

## 性能优化

### 测试策略
1. **分层测试**：
   - 高频使用源：每日测试
   - 低频使用源：每周测试
   - 历史源：每月测试

2. **智能缓存**：
   - 成功结果缓存1小时
   - 失败结果缓存30分钟
   - 动态调整缓存时间

3. **并行处理**：
   - 使用asyncio进行并发测试
   - 动态调整并发数
   - 失败源降级测试优先级

## 故障排除

### 常见问题

1. **自动发现未找到可用源**
   ```
   原因：网络连接问题或种子库不匹配
   解决：
   - 检查网络连接
   - 提供更具体的关键词
   - 手动添加新闻源
   ```

2. **测试成功率低**
   ```
   原因：目标网站限制或网络不稳定
   解决：
   - 增加测试超时时间
   - 降低并发测试数量
   - 禁用自动发现，手动维护
   ```

3. **白名单源数量不足**
   ```
   原因：自动清理过于严格
   解决：
   - 调整 min_success_rate 参数
   - 增加 failure_threshold
   - 运行 discover 命令发现新源
   ```

### 日志查看
所有操作都有详细日志，可在命令行中查看或配置日志级别。

## 开源准备

本skill已优化为可直接开源：

- ✅ 所有文件集中到skill目录
- ✅ 完整的文档说明
- ✅ 清晰的目录结构
- ✅ 零外部依赖（仅需aiohttp）
- ✅ 详细的配置示例
- ✅ 完整的命令行接口
- ✅ 预设种子库
- ✅ 性能优化策略

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request！

## 版本历史

- **v2.0** (2026-04-03)：增强白名单管理版
  - 首次运行自动发现
  - 动态维护机制
  - 统一配置管理
  - 完整命令行接口

- **v1.0**：基础新闻发布功能