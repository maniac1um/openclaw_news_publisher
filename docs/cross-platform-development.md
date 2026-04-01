# Windows 与 Ubuntu 双机开发说明

本文说明在 **Windows 11** 与 **Ubuntu 24.04 LTS** 上，基于同一 GitHub 仓库协作开发本项目的注意事项与推荐做法。

## 总体结论

- 使用 GitHub 作为单一源码来源，在两台机器上分别克隆、拉取、推送，**没有平台冲突**。
- 需要主动处理的是：**换行符、虚拟环境、环境变量、路径与 Git 配置**，避免「在本机正常、换系统就异常」。

## 1. 换行符（CRLF / LF）

| 系统 | 常见换行 |
|------|----------|
| Windows | CRLF |
| Linux（Ubuntu） | LF |

若混用，可能出现 diff 噪音、合并冲突增多，少数情况下脚本在 Linux 上执行异常。

**推荐：**

- 仓库根目录已提供 **`.gitattributes`**，约定文本文件以 **LF** 提交到远程（`* text=auto eol=lf`）。克隆后无需再手工加该文件。
- Windows 上可配合 `git config core.autocrlf`，与 `.gitattributes` 策略一致即可（常见为 `false` 或 `input`，避免与 `eol=lf` 重复转换）。

本项目以 Python 为主，业务代码对换行不敏感；仍建议统一策略，便于长期维护。

## 2. Python 与依赖

- 两台机器各自安装 **Python 3.11+**（与 `pyproject.toml` / README 一致）。
- **每台机器单独创建虚拟环境**，勿将 `venv` 提交到 Git。
- 在各自项目根目录执行：

```bash
python -m pip install -e ".[dev]"
```

- 若一台能跑、另一台报错，优先检查：Python 版本、是否执行了上述安装、是否在正确的 venv 中运行。

## 3. 启动服务

两台系统命令相同（在项目根目录、已激活 venv）：

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

开发时可加 `--reload`（仅开发环境）：

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 4. 环境变量与 `.env`

配置通过 `OPENCLAW_` 前缀及可选根目录 `.env` 加载（见 `app/core/config.py`）。

- **`.env` 通常含密钥，不应提交到 GitHub。** 在 Ubuntu 上需单独创建或导出环境变量。
- 两台机器可使用不同配置（例如本机关闭 `OPENCLAW_GIT_AUTO_PUSH`，服务器开启等）。
- 修改环境变量后需**重启 Uvicorn** 进程。

## 5. 路径与大小写

- Ubuntu 文件系统**区分大小写**；Windows 对部分场景不敏感。请保持仓库内路径、导入模块名大小写一致。
- 代码中应使用 **`pathlib`** 或正斜杠相对路径，避免写死 `D:\` 等 Windows 盘符。
- 报告数据目录默认为 `content/reports/raw` 与 `content/reports/rendered`，一般**不纳入版本库**；每台机器本地数据独立，按需备份或部署策略同步。

## 6. Git 与 GitHub

- Ubuntu 上新克隆后需单独配置 **Git 用户身份**（`user.name` / `user.email`）及 **GitHub 认证**（SSH 密钥或 HTTPS Token）。
- `scripts/publish_site.py` 依赖系统已安装的 **`git`**；在 Ubuntu 上需安装 `git` 并保证有提交权限（若启用自动 push，还需配置远程与凭据）。

## 7. 文档与联调示例

- README 中部分示例为 **PowerShell**；在 Ubuntu 上可使用 **curl**、**Python** 或自行改写为 bash，请求 URL 与 Header 保持一致即可。
- 中文 JSON 提交时建议使用 **UTF-8** 与 `Content-Type: application/json; charset=utf-8`，避免出现乱码或 `???`。

## 8. 防火墙与访问

- 若需从局域网其他设备访问 Ubuntu 上的服务，需放行对应端口（如 `8000`）或配置反向代理（Nginx 等）与 HTTPS。
- Windows 防火墙在对外暴露端口时同样需要放行规则。

## 9. 推荐阅读顺序

1. 根目录 [README.md](../README.md) — 功能、接口、快速开始  
2. [docs/api/openclaw-intake.md](api/openclaw-intake.md) — OpenClaw 接入契约  
3. [docs/architecture/news-pipeline.md](architecture/news-pipeline.md) — 处理流水线  
4. 本文 — 跨平台开发约定  
