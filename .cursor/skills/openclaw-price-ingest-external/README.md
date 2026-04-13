# openclaw-price-ingest-external

OpenClaw 侧完成价格采集与解析，向 OpenClaw News Publisher **`POST .../observations/ingest`** 自动入库；服务端默认不做监测网页抓取。价格默认以 **人民币（CNY）** 计价。

## 使用方式

在 Cursor / OpenClaw 中启用本技能（`SKILL.md` 所在目录），先完成文档中的 **「执行前配置清单」**（服务地址与 Key、keyword 或 monitor_id、数据源与 CNY 换算约定、定时与失败与日志），再执行 bootstrap → ingest →（可选）public 校验与 external-heartbeat。

## 文档

- 完整流程、安全准则、API 与 curl 示例：见同目录 **`SKILL.md`**。
